"""Restaurant opening hours and live open/closed status."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from apps.restaurants.models import Restaurant

DEFAULT_TZ = ZoneInfo("Africa/Addis_Ababa")


def _local_now(tz: ZoneInfo | None = None) -> datetime:
    return datetime.now(tz or DEFAULT_TZ)


def restaurant_is_open(
    restaurant: Restaurant,
    *,
    at: datetime | None = None,
) -> bool:
    if not restaurant.is_active:
        return False
    opens = getattr(restaurant, "opens_at", None)
    closes = getattr(restaurant, "closes_at", None)
    if opens is None or closes is None:
        return True

    now = at or _local_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=DEFAULT_TZ)
    current = now.time().replace(tzinfo=None)

    if opens <= closes:
        return opens <= current <= closes
    return current >= opens or current <= closes


def format_hours_display(opens_at: time | None, closes_at: time | None) -> str:
    if opens_at is None or closes_at is None:
        return ""
    return f"{_format_12h(opens_at)} – {_format_12h(closes_at)}"


def _format_12h(value: time) -> str:
    hour = value.hour % 12 or 12
    minute = value.minute
    suffix = "AM" if value.hour < 12 else "PM"
    if minute:
        return f"{hour}:{minute:02d} {suffix}"
    return f"{hour} {suffix}"
