"""
Central rules for whether a user may receive JWTs (token pair, refresh).

Uses a single client-facing error message to reduce account enumeration.
"""

from __future__ import annotations

from rest_framework.exceptions import AuthenticationFailed, ValidationError

from apps.drivers.models import DriverProfile
from core.models import User

_CLIENT_MSG = "Invalid credentials."
SUSPENDED_ACCOUNT_MESSAGE = "Your account is suspended."


def assert_jwt_eligible(user: User) -> None:
    """
    Raise ValidationError if this user must not be issued or refreshed tokens.

    Drivers must be approved; other roles only require an active account.
    All failures use the same message (anti-enumeration).
    """
    if not user.is_active:
        raise ValidationError(_CLIENT_MSG)

    if user.role != User.Role.DRIVER:
        return

    try:
        profile = user.driver_profile
    except DriverProfile.DoesNotExist:
        raise ValidationError(_CLIENT_MSG)

    if profile.approval_status == DriverProfile.ApprovalStatus.APPROVED:
        return

    if profile.approval_status == DriverProfile.ApprovalStatus.SUSPENDED:
        raise ValidationError(SUSPENDED_ACCOUNT_MESSAGE)

    raise ValidationError(_CLIENT_MSG)


def enforce_jwt_eligible(user: User) -> None:
    """
    Same rules as ``assert_jwt_eligible`` for per-request JWT authentication.

    Raises AuthenticationFailed (401) so clients treat ineligible sessions as logged out.
    """
    try:
        assert_jwt_eligible(user)
    except ValidationError as exc:
        detail = exc.detail
        if isinstance(detail, list):
            message = str(detail[0]) if detail else _CLIENT_MSG
        else:
            message = str(detail)
        raise AuthenticationFailed(message) from exc
