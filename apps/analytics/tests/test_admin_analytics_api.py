from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from django.test import TestCase

from apps.orders.models import DriverDeliveryEvent, Order
from apps.payments.models import Payment
from apps.restaurants.models import MenuCategory, MenuItem, Restaurant
from core.models import User


class AdminAnalyticsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(phone="+251900000001", password="ComplexPass1!", role=User.Role.ADMIN)
        self.sales = User.objects.create_user(phone="+251900000002", password="ComplexPass1!", role=User.Role.SALES)
        self.customer = User.objects.create_user(
            phone="+251900000003", password="ComplexPass1!", role=User.Role.CUSTOMER
        )
        self.driver_one = User.objects.create_user(
            phone="+251900000004", password="ComplexPass1!", role=User.Role.DRIVER
        )
        self.driver_two = User.objects.create_user(
            phone="+251900000005", password="ComplexPass1!", role=User.Role.DRIVER
        )
        self.restaurant = Restaurant.objects.create(
            name="Analytics Bistro",
            latitude=Decimal("9.030000"),
            longitude=Decimal("38.740000"),
            is_active=True,
        )
        category = MenuCategory.objects.create(restaurant=self.restaurant, name="Main")
        self.menu_item = MenuItem.objects.create(
            restaurant=self.restaurant,
            category=category,
            name="Kitfo",
            price=Decimal("180.00"),
            currency="ETB",
            is_available=True,
        )

    def _create_order_with_payment(
        self,
        *,
        reference: str,
        amount: Decimal,
        paid_at,
        driver: User | None = None,
        delivered: bool = False,
    ) -> Order:
        order = Order.objects.create(
            reference=reference,
            customer=self.customer,
            restaurant=self.restaurant,
            assigned_driver=driver,
            status=Order.Status.DELIVERED if delivered else Order.Status.CONFIRMED,
            payment_status=Order.PaymentStatus.PAID,
            subtotal=amount - Decimal("30.00"),
            delivery_fee=Decimal("30.00"),
            total_amount=amount,
            delivery_address={"receiver_name": "Test", "phone": "0900", "address_line": "Addis"},
        )
        Payment.objects.create(
            order=order,
            customer=self.customer,
            amount=amount,
            currency="ETB",
            chapa_tx_ref=f"TX-{reference}",
            status=Payment.Status.SUCCESS,
            paid_at=paid_at,
        )
        if delivered and driver:
            DriverDeliveryEvent.objects.create(
                order=order,
                driver=driver,
                action=DriverDeliveryEvent.Action.COMPLETED,
                created_at=paid_at,
            )
        return order

    def test_revenue_analytics_aggregates_successful_payments(self):
        now = timezone.now()
        self._create_order_with_payment(
            reference="KD-A-1001",
            amount=Decimal("200.00"),
            paid_at=now - timedelta(days=1),
            driver=self.driver_one,
            delivered=True,
        )
        self._create_order_with_payment(
            reference="KD-A-1002",
            amount=Decimal("150.00"),
            paid_at=now,
            driver=self.driver_two,
            delivered=True,
        )

        self.client.force_authenticate(user=self.admin)
        res = self.client.get(
            "/api/v1/admin/analytics/revenue/",
            {"start_date": (timezone.localdate() - timedelta(days=2)).isoformat(), "end_date": timezone.localdate().isoformat()},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = res.json()
        self.assertEqual(body["currency"], "ETB")
        self.assertEqual(body["totals"]["successful_payments_count"], 2)
        self.assertEqual(body["totals"]["orders_count"], 2)
        self.assertEqual(Decimal(body["totals"]["revenue_total"]), Decimal("350.00"))
        self.assertGreaterEqual(len(body["trends"]), 1)

    def test_revenue_analytics_empty_dataset(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/admin/analytics/revenue/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = res.json()
        self.assertEqual(Decimal(body["totals"]["revenue_total"]), Decimal("0.00"))
        self.assertEqual(body["totals"]["successful_payments_count"], 0)
        self.assertEqual(body["top_restaurants"], [])

    def test_driver_payout_report_supports_driver_filter(self):
        now = timezone.now()
        self._create_order_with_payment(
            reference="KD-A-1003",
            amount=Decimal("280.00"),
            paid_at=now,
            driver=self.driver_one,
            delivered=True,
        )
        self._create_order_with_payment(
            reference="KD-A-1004",
            amount=Decimal("320.00"),
            paid_at=now,
            driver=self.driver_two,
            delivered=True,
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(
            "/api/v1/admin/analytics/drivers/",
            {
                "start_date": (timezone.localdate() - timedelta(days=1)).isoformat(),
                "end_date": timezone.localdate().isoformat(),
                "driver_id": self.driver_one.id,
            },
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = res.json()
        self.assertEqual(len(body["drivers"]), 1)
        self.assertEqual(body["drivers"][0]["driver_id"], self.driver_one.id)
        self.assertEqual(Decimal(body["summary"]["driver_payout_total"]), Decimal("30.00"))

    def test_platform_profit_calculation(self):
        now = timezone.now()
        self._create_order_with_payment(
            reference="KD-A-1005",
            amount=Decimal("300.00"),
            paid_at=now,
            driver=self.driver_one,
            delivered=True,
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/admin/analytics/platform-profit/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = res.json()
        self.assertEqual(Decimal(body["totals"]["gross_revenue"]), Decimal("300.00"))
        self.assertEqual(Decimal(body["totals"]["driver_payout_total"]), Decimal("30.00"))
        self.assertEqual(Decimal(body["totals"]["estimated_platform_profit"]), Decimal("270.00"))

    def test_admin_only_rbac(self):
        self.client.force_authenticate(user=self.sales)
        res = self.client.get("/api/v1/admin/analytics/revenue/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
