"""Phone OTP for driver onboarding (stored in Redis/cache)."""

from __future__ import annotations

import logging
import random
import secrets

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("kech.auth")

_PREFIX = "otp:"
_TTL_SECONDS = 60 * 5
_MAX_ATTEMPTS = 5


class OtpError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _cache_key(*, purpose: str, phone: str) -> str:
    return f"{_PREFIX}{purpose}:{phone}"


def send_code(*, purpose: str, phone: str) -> None:
    """Generate and store a 6-digit OTP. In DEBUG, log the code (no SMS provider yet)."""
    code = f"{random.randint(0, 999999):06d}"
    cache.set(
        _cache_key(purpose=purpose, phone=phone),
        {"code": code, "attempts": 0},
        timeout=_TTL_SECONDS,
    )
    if settings.DEBUG:
        logger.info(
            "otp.sent.debug",
            extra={"purpose": purpose, "masked_phone": phone[-4:], "code": code},
        )
    # Production: integrate SMS provider (Twilio, etc.) here.


def verify_code(*, purpose: str, phone: str, code: str) -> None:
    entry = cache.get(_cache_key(purpose=purpose, phone=phone))
    if not entry:
        raise OtpError("Code expired or not found. Request a new code.", status_code=400)

    attempts = int(entry.get("attempts", 0))
    if attempts >= _MAX_ATTEMPTS:
        cache.delete(_cache_key(purpose=purpose, phone=phone))
        raise OtpError("Too many attempts. Request a new code.", status_code=429)

    if not secrets.compare_digest(str(entry.get("code", "")), str(code).strip()):
        entry["attempts"] = attempts + 1
        cache.set(_cache_key(purpose=purpose, phone=phone), entry, timeout=_TTL_SECONDS)
        raise OtpError("Invalid verification code.", status_code=400)

    cache.delete(_cache_key(purpose=purpose, phone=phone))
