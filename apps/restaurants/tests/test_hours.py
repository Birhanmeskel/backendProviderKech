from datetime import datetime, time
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase

from apps.restaurants.models import Restaurant
from apps.restaurants.services.hours import restaurant_is_open

TZ = ZoneInfo("Africa/Addis_Ababa")


class RestaurantHoursTests(TestCase):
    def _restaurant(self, *, opens: time, closes: time, is_active: bool = True) -> Restaurant:
        return Restaurant.objects.create(
            name="Hours Test",
            latitude=Decimal("9.000000"),
            longitude=Decimal("38.000000"),
            opens_at=opens,
            closes_at=closes,
            is_active=is_active,
        )

    def test_open_during_business_hours(self):
        restaurant = self._restaurant(opens=time(9, 0), closes=time(22, 0))
        noon = datetime(2026, 5, 20, 12, 0, tzinfo=TZ)
        self.assertTrue(restaurant_is_open(restaurant, at=noon))

    def test_closed_outside_business_hours(self):
        restaurant = self._restaurant(opens=time(9, 0), closes=time(22, 0))
        late = datetime(2026, 5, 20, 23, 0, tzinfo=TZ)
        self.assertFalse(restaurant_is_open(restaurant, at=late))

    def test_inactive_restaurant_always_closed(self):
        restaurant = self._restaurant(opens=time(9, 0), closes=time(22, 0), is_active=False)
        noon = datetime(2026, 5, 20, 12, 0, tzinfo=TZ)
        self.assertFalse(restaurant_is_open(restaurant, at=noon))

    def test_public_list_exposes_is_open(self):
        self._restaurant(opens=time(9, 0), closes=time(22, 0))
        noon = datetime(2026, 5, 20, 12, 0, tzinfo=TZ)
        with patch("apps.restaurants.services.hours._local_now", return_value=noon):
            res = self.client.get("/api/v1/restaurants/")
        self.assertEqual(res.status_code, 200)
        row = res.json()[0]
        self.assertIn("is_open", row)
        self.assertTrue(row["is_open"])
