"""
JWT authentication with per-request eligibility enforcement.

Extends SimpleJWT so suspended/rejected/inactive drivers lose API access immediately,
not only on the next login or refresh attempt.
"""

from __future__ import annotations

from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.users.auth_policy import enforce_jwt_eligible


class SafeJWTAuthentication(JWTAuthentication):
    """
    Validate JWT, load user, then re-apply the same rules used at token issuance.

    Without this, an access token issued before suspension remains valid until expiry.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        enforce_jwt_eligible(user)
        return user
