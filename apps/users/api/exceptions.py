"""
DRF exception handler: anti-enumeration responses on sensitive auth routes.

Maps most client/validation failures on token + register paths to a single message.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.exceptions import Throttled, ValidationError

from apps.users import auth_logging
from apps.users.auth_policy import SUSPENDED_ACCOUNT_MESSAGE

_AUTH_PREFIX = "/api/v1/auth/"
_DETAIL = "Invalid credentials."


def _auth_subpath(path: str) -> str:
    if not path.startswith(_AUTH_PREFIX):
        return ""
    return path.removeprefix(_AUTH_PREFIX).rstrip("/")


def _should_mask_path(path: str) -> bool:
    sub = _auth_subpath(path)
    if sub == "token" or sub.startswith("token/"):
        return True
    if sub.startswith("register"):
        return True
    return False


def _extract_detail_message(payload: object) -> str | None:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list) and payload:
        return str(payload[0])
    if isinstance(payload, dict):
        for key in ("detail", "non_field_errors"):
            if key in payload:
                message = _extract_detail_message(payload[key])
                if message:
                    return message
    return None


def auth_safe_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    request = context.get("request")
    if request is None or not _should_mask_path(request.path):
        return response

    if isinstance(exc, Throttled):
        return response

    if response is None:
        return response

    if response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        return response

    if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return response

    phone = None
    if hasattr(request, "data") and isinstance(request.data, dict):
        phone = request.data.get("phone")

    sub = _auth_subpath(request.path)
    
    # Allow field-specific validation errors to pass through for register only
    # (e.g., {"password": ["too common"], "phone": ["already exists"]}).
    if sub.startswith("register") and isinstance(exc, ValidationError) and isinstance(exc.detail, dict):
        auth_logging.log_register_failure(phone, response.status_code)
        return response
    
    exposed = _extract_detail_message(exc.detail if isinstance(exc, ValidationError) else None)
    if exposed is None and response is not None:
        exposed = _extract_detail_message(response.data)

    if exposed == SUSPENDED_ACCOUNT_MESSAGE:
        auth_logging.log_token_failure(phone, response.status_code)
        return Response({"detail": SUSPENDED_ACCOUNT_MESSAGE}, status=response.status_code)

    # Mask all other errors as generic "Invalid credentials."
    if sub.startswith("register"):
        auth_logging.log_register_failure(phone, response.status_code)
    else:
        auth_logging.log_token_failure(phone, response.status_code)

    return Response({"detail": _DETAIL}, status=response.status_code)
