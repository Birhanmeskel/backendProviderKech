"""Delivery pricing — distance, tiered driver payout, fixed platform fee."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from math import asin, ceil, cos, radians, sin, sqrt

EARTH_RADIUS_KM = Decimal("6371")

# Driver payout per tier, in ETB.
#   Index 0 -> 0–1 km, index 1 -> 1–2 km, ..., index 9 -> 9–10 km.
TIERS: tuple[Decimal, ...] = (
    Decimal("50"),
    Decimal("65"),
    Decimal("75"),
    Decimal("100"),
    Decimal("125"),
    Decimal("150"),
    Decimal("175"),
    Decimal("200"),
    Decimal("225"),
    Decimal("250"),
)

# Beyond the table, driver payout grows by this much per additional km.
PER_KM_BEYOND_TABLE = Decimal("25")

# Fixed platform fee added on top of the driver payout for every order.
PLATFORM_FEE = Decimal("10.00")

_TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class DeliveryPricing:
    distance_km: Decimal | None
    driver_payout: Decimal
    platform_fee: Decimal
    delivery_fee: Decimal

    def as_dict(self) -> dict[str, str | None]:
        return {
            "distance_km": str(self.distance_km) if self.distance_km is not None else None,
            "driver_payout": str(self.driver_payout),
            "platform_fee": str(self.platform_fee),
            "delivery_fee": str(self.delivery_fee),
        }


def haversine_km(
    lat1: float | Decimal,
    lon1: float | Decimal,
    lat2: float | Decimal,
    lon2: float | Decimal,
) -> Decimal:
    """Great-circle distance between two coordinates, in kilometres."""
    lat1f, lon1f, lat2f, lon2f = (float(v) for v in (lat1, lon1, lat2, lon2))
    rlat1, rlon1, rlat2, rlon2 = (radians(v) for v in (lat1f, lon1f, lat2f, lon2f))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    km = Decimal(c) * EARTH_RADIUS_KM
    return km.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def driver_payout_for_distance(distance_km: Decimal) -> Decimal:
    """Tiered driver payout. `distance_km <= 0` falls into the first tier."""
    if distance_km <= 0:
        return TIERS[0]
    tier_index = ceil(float(distance_km))  # 0.1 km -> 1 (tier 0); 1.0 -> 1; 1.01 -> 2
    if tier_index <= len(TIERS):
        return TIERS[tier_index - 1]
    extra_km = tier_index - len(TIERS)
    return TIERS[-1] + PER_KM_BEYOND_TABLE * Decimal(extra_km)


def apply_driver_percentage(delivery_fee: Decimal, payout_percentage: Decimal) -> tuple[Decimal, Decimal]:
    """Split delivery_fee into (driver_payout, platform_fee) using the driver's percentage."""
    driver_payout = (delivery_fee * payout_percentage / Decimal("100")).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    platform_fee = (delivery_fee - driver_payout).quantize(_TWO_PLACES)
    return driver_payout, platform_fee


def compute_pricing(distance_km: Decimal | None) -> DeliveryPricing:
    """Build the financial snapshot. `None` distance falls back to the 0–1 km tier."""
    if distance_km is None or distance_km < 0:
        driver_payout = TIERS[0]
        effective_distance: Decimal | None = None
    else:
        driver_payout = driver_payout_for_distance(distance_km)
        effective_distance = distance_km
    delivery_fee = (driver_payout + PLATFORM_FEE).quantize(_TWO_PLACES)
    return DeliveryPricing(
        distance_km=effective_distance,
        driver_payout=driver_payout.quantize(_TWO_PLACES),
        platform_fee=PLATFORM_FEE.quantize(_TWO_PLACES),
        delivery_fee=delivery_fee,
    )
