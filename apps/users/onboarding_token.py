"""Short-lived registration tokens for driver onboarding (documents, OTP, status)."""

from __future__ import annotations

import secrets

from django.core.cache import cache

_PREFIX = "driver_onboarding:"
_TTL_SECONDS = 60 * 60 * 24  # 24 hours


def issue(*, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    cache.set(f"{_PREFIX}{token}", user_id, timeout=_TTL_SECONDS)
    return token


def resolve_user_id(token: str | None) -> int | None:
    if not token or not str(token).strip():
        return None
    value = cache.get(f"{_PREFIX}{token.strip()}")
    if value is None:
        return None
    return int(value)


def revoke(token: str | None) -> None:
    if token and str(token).strip():
        cache.delete(f"{_PREFIX}{token.strip()}")
