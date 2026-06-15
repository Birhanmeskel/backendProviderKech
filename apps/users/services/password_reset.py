"""Password reset via phone + registered recovery email (OTP in cache; email send TBD)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.users.otp_service import OtpError, send_code, verify_code
from apps.users.phone_utils import normalize_phone
from core.models import User

logger = logging.getLogger("kech.auth")

_PURPOSE = "password_reset"


class PasswordResetError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_recovery_email(user: User) -> str:
    if user.role == User.Role.CUSTOMER:
        profile = getattr(user, "customer_profile", None)
        return (profile.email if profile else "").strip()
    if user.role == User.Role.DRIVER:
        profile = getattr(user, "driver_profile", None)
        return (profile.email if profile else "").strip()
    return (getattr(user, "recovery_email", None) or "").strip()


def request_password_reset(*, phone: str, email: str) -> dict:
    """Validate phone/email match, store OTP. Returns non-sensitive hints for the client."""
    try:
        normalized_phone = normalize_phone(phone, obscure_invalid_format=True)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        if isinstance(detail, list) and detail:
            msg = str(detail[0])
        else:
            msg = str(detail)
        raise PasswordResetError(msg) from exc

    email_norm = email.strip().lower()
    if not email_norm:
        raise PasswordResetError("Email is required.", status_code=400)

    try:
        user = User.objects.get(phone=normalized_phone, is_active=True)
    except User.DoesNotExist:
        # Avoid account enumeration — same response shape as mismatch
        raise PasswordResetError(
            "If this phone and email match our records, a verification code was sent.",
            status_code=200,
        )

    registered = get_recovery_email(user).strip().lower()
    if not registered:
        raise PasswordResetError(
            "No recovery email is on file for this account. Update your profile email or contact support.",
            status_code=400,
        )
    if registered != email_norm:
        raise PasswordResetError(
            "If this phone and email match our records, a verification code was sent.",
            status_code=200,
        )

    send_code(purpose=_PURPOSE, phone=normalized_phone)
    if settings.DEBUG:
        logger.info(
            "password_reset.otp.debug",
            extra={"phone_suffix": normalized_phone[-4:], "email": email_norm},
        )

    payload: dict = {
        "message": "Verification code sent to your email.",
        "phone": normalized_phone,
    }
    if settings.DEBUG:
        payload["debug_note"] = "In development, check server logs for the OTP code."
    return payload


def confirm_password_reset(*, phone: str, email: str, code: str, new_password: str) -> None:
    try:
        normalized_phone = normalize_phone(phone, obscure_invalid_format=True)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        if isinstance(detail, list) and detail:
            msg = str(detail[0])
        else:
            msg = str(detail)
        raise PasswordResetError(msg) from exc

    email_norm = email.strip().lower()
    try:
        user = User.objects.get(phone=normalized_phone, is_active=True)
    except User.DoesNotExist:
        raise PasswordResetError("Invalid or expired verification code.", status_code=400)

    registered = get_recovery_email(user).strip().lower()
    if not registered or registered != email_norm:
        raise PasswordResetError("Invalid or expired verification code.", status_code=400)

    try:
        verify_code(purpose=_PURPOSE, phone=normalized_phone, code=code)
    except OtpError as exc:
        raise PasswordResetError(exc.message, status_code=exc.status_code) from exc

    try:
        validate_password(new_password, user=user)
    except DjangoValidationError as exc:
        raise PasswordResetError(" ".join(exc.messages), status_code=400) from exc

    user.set_password(new_password)
    user.save(update_fields=["password"])
