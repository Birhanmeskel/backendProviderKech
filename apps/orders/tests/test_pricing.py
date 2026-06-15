from decimal import Decimal

from django.test import SimpleTestCase

from apps.orders.services.pricing import (
    PER_KM_BEYOND_TABLE,
    PLATFORM_FEE,
    TIERS,
    compute_pricing,
    driver_payout_for_distance,
    haversine_km,
)


class DriverPayoutTierTests(SimpleTestCase):
    def test_within_table_tiers(self):
        cases = [
            (Decimal("0"), TIERS[0]),
            (Decimal("0.5"), TIERS[0]),
            (Decimal("1"), TIERS[0]),
            (Decimal("1.01"), TIERS[1]),
            (Decimal("2"), TIERS[1]),
            (Decimal("2.5"), TIERS[2]),
            (Decimal("3"), TIERS[2]),
            (Decimal("3.5"), TIERS[3]),
            (Decimal("9.99"), TIERS[9]),
            (Decimal("10"), TIERS[9]),
        ]
        for km, expected in cases:
            with self.subTest(km=km):
                self.assertEqual(driver_payout_for_distance(km), expected)

    def test_beyond_table_adds_per_km(self):
        # 10.01 km -> ceil = 11 -> 250 + 25 * 1
        self.assertEqual(
            driver_payout_for_distance(Decimal("10.01")),
            TIERS[-1] + PER_KM_BEYOND_TABLE,
        )
        # 12.4 km -> ceil = 13 -> 250 + 25 * 3
        self.assertEqual(
            driver_payout_for_distance(Decimal("12.4")),
            TIERS[-1] + PER_KM_BEYOND_TABLE * 3,
        )


class ComputePricingTests(SimpleTestCase):
    def test_falls_back_to_first_tier_when_distance_none(self):
        pricing = compute_pricing(None)
        self.assertIsNone(pricing.distance_km)
        self.assertEqual(pricing.driver_payout, TIERS[0].quantize(Decimal("0.01")))
        self.assertEqual(pricing.platform_fee, PLATFORM_FEE.quantize(Decimal("0.01")))
        self.assertEqual(
            pricing.delivery_fee,
            (TIERS[0] + PLATFORM_FEE).quantize(Decimal("0.01")),
        )

    def test_known_distance(self):
        pricing = compute_pricing(Decimal("4.2"))
        # ceil(4.2) = 5 -> tier index 4 -> 125
        self.assertEqual(pricing.driver_payout, Decimal("125.00"))
        self.assertEqual(pricing.platform_fee, Decimal("10.00"))
        self.assertEqual(pricing.delivery_fee, Decimal("135.00"))

    def test_far_distance_uses_per_km_rate(self):
        # 13 km -> 250 + 25*3 = 325 driver payout, 335 total
        pricing = compute_pricing(Decimal("13"))
        self.assertEqual(pricing.driver_payout, Decimal("325.00"))
        self.assertEqual(pricing.delivery_fee, Decimal("335.00"))


class HaversineTests(SimpleTestCase):
    def test_zero_distance_for_same_point(self):
        self.assertEqual(haversine_km(9.0, 38.0, 9.0, 38.0), Decimal("0.000"))

    def test_short_distance_is_plausible(self):
        # ~1.4 km between (9.020, 38.770) and (9.025, 38.780) at this latitude.
        km = haversine_km(9.020, 38.770, 9.025, 38.780)
        self.assertGreater(km, Decimal("1.0"))
        self.assertLess(km, Decimal("1.7"))
