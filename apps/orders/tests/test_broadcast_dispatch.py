from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.drivers.models import DriverProfile
from apps.orders.models import Order
from apps.orders.services.order import accept_order, OrderServiceError
from apps.restaurants.models import MenuCategory, MenuItem, Restaurant
from core.models import User


def _make_driver(phone: str, *, approved=True, online=True) -> User:
    user = User.objects.create_user(phone=phone, password="ComplexPass1!", role=User.Role.DRIVER)
    DriverProfile.objects.create(
        user=user,
        full_name=f"Driver {phone}",
        vehicle_type=DriverProfile.VehicleType.MOTORBIKE,
        approval_status=(
            DriverProfile.ApprovalStatus.APPROVED if approved else DriverProfile.ApprovalStatus.PENDING
        ),
        operational_status=(
            DriverProfile.OperationalStatus.ONLINE if online else DriverProfile.OperationalStatus.OFFLINE
        ),
    )
    return user


def _make_order_in_search() -> Order:
    customer = User.objects.create_user(
        phone="+25190000001", password="ComplexPass1!", role=User.Role.CUSTOMER
    )
    restaurant = Restaurant.objects.create(
        name="Atlas",
        address_text="Bole",
        latitude=Decimal("9.020"),
        longitude=Decimal("38.770"),
        is_active=True,
    )
    category = MenuCategory.objects.create(restaurant=restaurant, name="Mains", is_active=True)
    MenuItem.objects.create(
        category=category,
        restaurant=restaurant,
        name="Burger",
        price=Decimal("100.00"),
        is_available=True,
    )
    return Order.objects.create(
        reference="KD-T0001",
        customer=customer,
        restaurant=restaurant,
        status=Order.Status.SEARCHING_DRIVER,
        payment_status=Order.PaymentStatus.PAID,
        delivery_address={"receiver_name": "C", "phone": "+25190000001", "address_line": "X"},
        delivery_fee=Decimal("60.00"),
        driver_payout=Decimal("50.00"),
        platform_fee=Decimal("10.00"),
    )


class AvailableOrdersFeedTests(TestCase):
    def setUp(self):
        self.driver = _make_driver("+25190000010")
        self.client = APIClient()
        self.client.force_authenticate(self.driver)

    def test_shows_paid_searching_unassigned_orders(self):
        order = _make_order_in_search()
        res = self.client.get("/api/v1/drivers/orders/available/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in res.json()["results"]]
        self.assertIn(order.id, ids)

    def test_hides_already_assigned_orders(self):
        order = _make_order_in_search()
        order.assigned_driver = self.driver
        order.status = Order.Status.ASSIGNED
        order.save(update_fields=["assigned_driver", "status"])
        res = self.client.get("/api/v1/drivers/orders/available/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["results"], [])


class ClaimOrderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.driver = _make_driver("+25190000020")

    def test_first_driver_wins_second_gets_409(self):
        order = _make_order_in_search()
        other = _make_driver("+25190000021")

        c1 = APIClient(); c1.force_authenticate(self.driver)
        c2 = APIClient(); c2.force_authenticate(other)

        res1 = c1.post(f"/api/v1/drivers/orders/{order.id}/claim/")
        res2 = c2.post(f"/api/v1/drivers/orders/{order.id}/claim/")

        # Exactly one accept succeeds.
        outcomes = sorted([res1.status_code, res2.status_code])
        self.assertEqual(outcomes, [200, 409])

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.ASSIGNED)
        self.assertIsNotNone(order.assigned_driver_id)

    def test_offline_driver_cannot_claim(self):
        order = _make_order_in_search()
        offline = _make_driver("+25190000022", online=False)
        client = APIClient(); client.force_authenticate(offline)
        res = client.post(f"/api/v1/drivers/orders/{order.id}/claim/")
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        order.refresh_from_db()
        self.assertIsNone(order.assigned_driver_id)

    def test_unapproved_driver_cannot_claim(self):
        order = _make_order_in_search()
        pending = _make_driver("+25190000023", approved=False)
        client = APIClient(); client.force_authenticate(pending)
        res = client.post(f"/api/v1/drivers/orders/{order.id}/claim/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_busy_driver_can_still_claim(self):
        # Driver currently on one active delivery (status=busy) should
        # remain eligible for additional broadcast orders, up to MAX.
        busy = _make_driver("+25190000025")
        busy.driver_profile.operational_status = DriverProfile.OperationalStatus.BUSY
        busy.driver_profile.save(update_fields=["operational_status"])
        order = _make_order_in_search()
        client = APIClient(); client.force_authenticate(busy)
        res = client.post(f"/api/v1/drivers/orders/{order.id}/claim/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.assigned_driver_id, busy.id)
        self.assertEqual(order.status, Order.Status.ASSIGNED)

    def test_service_raises_when_already_assigned(self):
        order = _make_order_in_search()
        other = _make_driver("+25190000024")
        order.assigned_driver = other
        order.status = Order.Status.ASSIGNED
        order.save(update_fields=["assigned_driver", "status"])
        with self.assertRaises(OrderServiceError):
            accept_order(order_id=order.id, driver=self.driver)
