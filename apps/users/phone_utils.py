"""
Phone normalization for auth and storage (single canonical form per account).

Accepted format is international E.164-like: +<digits> (max 15 digits).
Examples: +251983204356, +14155552671.
"""

from __future__ import annotations

import re

from rest_framework.exceptions import ValidationError

_ENUM_MSG = "Invalid credentials."
_E164_MSG = (
    "Phone must be E.164: '+' then country code and subscriber number "
    "(8–15 digits after '+', no spaces). Examples: +251983204356, +14155552671."
)


def normalize_phone(phone: str | None, *, obscure_invalid_format: bool = False) -> str:
    """
    Normalize to canonical stored form. Rejects non-E.164 input.

    Login flows pass ``obscure_invalid_format=True`` so malformed phones get the same
    generic message as wrong passwords (no format oracle). Shell / registration / ORM
    use the default and get an explicit E.164 hint (e.g. ``createsuperuser``).
    """
    if phone is None or not str(phone).strip():
        raise ValidationError(_ENUM_MSG)
    value = str(phone).strip()
    if not re.fullmatch(r"\+[1-9]\d{7,14}", value):
        raise ValidationError(_ENUM_MSG if obscure_invalid_format else _E164_MSG)
    return value
