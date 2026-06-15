"""Driver onboarding permissions (registration token header)."""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.users.onboarding_token import resolve_user_id

REGISTRATION_TOKEN_HEADER = "X-Registration-Token"


class HasDriverOnboardingToken(BasePermission):
    """Allow requests that present a valid driver registration token."""

    def has_permission(self, request, view) -> bool:
        token = request.headers.get(REGISTRATION_TOKEN_HEADER) or request.META.get(
            f"HTTP_{REGISTRATION_TOKEN_HEADER.upper().replace('-', '_')}"
        )
        user_id = resolve_user_id(token)
        if user_id is None:
            return False
        request.onboarding_user_id = user_id  # type: ignore[attr-defined]
        request.registration_token = token  # type: ignore[attr-defined]
        return True
