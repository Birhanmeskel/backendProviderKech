from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.drivers.models import DriverProfile
from apps.orders.models import Order
from apps.restaurants.models import MenuCategory, MenuItem, Restaurant
from core.models import User


class DriverDeliveryApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            phone="+73000000001",
            password="ComplexPass1!",
            role=User.Role.CUSTOMER,
        )
        self.sales = User.objects.create_user(
            phone="+73000000003",
            password="ComplexPass1!",
            role=User.Role.SALES,
        )
        self.driver = User.objects.create_user(
            phone="+73000000005",
            password="ComplexPass1!",
            role=User.Role.DRIVER,
        )
        self.other_driver = User.objects.create_user(
            phone="+73000000006",
            password="ComplexPass1!",
            role=User.Role.DRIVER,
        )
        self.profile = DriverProfile.objects.create(
            user=self.driver,
            full_name="Driver One",
            approval_status=DriverProfile.ApprovalStatus.APPROVED,
            operational_status=DriverProfile.OperationalStatus.ONLINE,
        )
        DriverProfile.objects.create(
            user=self.other_driver,
            full_name="Driver Two",
            approval_status=DriverProfile.ApprovalStatus.APPROVED,
            operational_status=DriverProfile.OperationalStatus.ONLINE,
        )
        self.restaurant = Restaurant.objects.create(
            name="Test Bistro",
            latitude=Decimal("31.62"),
            longitude=Decimal("-7.98"),
            is_active=True,
        )
        category = MenuCategory.objects.create(restaurant=self.restaurant, name="Mains")
        self.menu_item = MenuItem.objects.create(
            restaurant=self.restaurant,
            category=category,
            name="Tagine",
            price=Decimal("85.00"),
            is_available=True,
        )
        self.client.force_authenticate(user=self.sales)
        res = self.client.post(
            "/api/v1/orders/",
            {
                "customer_id": self.customer.id,
                "restaurant_id": self.restaurant.id,
                "items": [{"menu_item_id": self.menu_item.id, "quantity": 1}],
                "delivery_address": {
                    "receiver_name": "Amina",
                    "phone": "+212600000000",
                    "address_line": "Gueliz",
                },
            },
            format="json",
        )
        self.order_id = res.json()["id"]
        self.client.post(
            f"/api/v1/orders/{self.order_id}/assign-driver/",
            {"driver_id": self.driver.id},
            format="json",
        )
        self.client.force_authenticate(user=self.driver)

    def test_availability_toggle(self):
        res = self.client.get("/api/v1/drivers/me/availability/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["operational_status"], "busy")

        blocked = self.client.patch(
            "/api/v1/drivers/me/availability/",
            {"operational_status": "offline"},
            format="json",
        )
        self.assertEqual(blocked.status_code, status.HTTP_409_CONFLICT)

    def test_accept_pickup_deliver_flow(self):
        accept = self.client.post(f"/api/v1/drivers/orders/{self.order_id}/accept/")
        self.assertEqual(accept.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(accept.json()["driver_acknowledged_at"])
        self.assertEqual(accept.json()["status"], Order.Status.ASSIGNED)

        pickup = self.client.post(f"/api/v1/drivers/orders/{self.order_id}/pickup/")
        self.assertEqual(pickup.status_code, status.HTTP_200_OK)
        self.assertEqual(pickup.json()["status"], Order.Status.PICKED_UP)

        start = self.client.post(f"/api/v1/drivers/orders/{self.order_id}/start-delivery/")
        self.assertEqual(start.status_code, status.HTTP_200_OK)
        self.assertEqual(start.json()["status"], Order.Status.DELIVERING)

        complete = self.client.post(f"/api/v1/drivers/orders/{self.order_id}/complete/")
        self.assertEqual(complete.status_code, status.HTTP_200_OK)
        self.assertEqual(complete.json()["status"], Order.Status.DELIVERED)

        again = self.client.post(f"/api/v1/drivers/orders/{self.order_id}/complete/")
        self.assertEqual(again.status_code, status.HTTP_409_CONFLICT)

    def test_offline_driver_blocked(self):
        self.profile.operational_status = DriverProfile.OperationalStatus.OFFLINE
        self.profile.save(update_fields=["operational_status"])
        res = self.client.post(f"/api/v1/drivers/orders/{self.order_id}/pickup/")
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_driver_decline_sets_declined_status(self):
        decline = self.client.post(f"/api/v1/drivers/orders/{self.order_id}/decline/")
        self.assertEqual(decline.status_code, status.HTTP_200_OK)
        self.assertEqual(decline.json()["status"], Order.Status.DECLINED)

        pickup = self.client.post(f"/api/v1/drivers/orders/{self.order_id}/pickup/")
        self.assertEqual(pickup.status_code, status.HTTP_409_CONFLICT)

    def test_reassign_different_driver_after_decline(self):
        decline = self.client.post(f"/api/v1/drivers/orders/{self.order_id}/decline/")
        self.assertEqual(decline.status_code, status.HTTP_200_OK)
        self.assertEqual(decline.json()["status"], Order.Status.DECLINED)

        self.client.force_authenticate(user=self.sales)
        reassign = self.client.post(
            f"/api/v1/orders/{self.order_id}/assign-driver/",
            {"driver_id": self.other_driver.id},
            format="json",
        )
        self.assertEqual(reassign.status_code, status.HTTP_200_OK)
        self.assertEqual(reassign.json()["status"], Order.Status.ASSIGNED)
        self.assertEqual(reassign.json()["assigned_driver"], self.other_driver.id)

    def test_cannot_reassign_declined_order_to_same_driver(self):
        self.client.post(f"/api/v1/drivers/orders/{self.order_id}/decline/")
        self.client.force_authenticate(user=self.sales)
        again = self.client.post(
            f"/api/v1/orders/{self.order_id}/assign-driver/",
            {"driver_id": self.driver.id},
            format="json",
        )
        self.assertEqual(again.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("declined", again.json()["detail"].lower())

    def test_other_driver_cannot_access_order(self):
        self.client.force_authenticate(user=self.other_driver)
        res = self.client.get(f"/api/v1/drivers/orders/{self.order_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_assign_requires_online_driver(self):
        offline = User.objects.create_user(
            phone="+73000000007",
            password="ComplexPass1!",
            role=User.Role.DRIVER,
        )
        DriverProfile.objects.create(
            user=offline,
            full_name="Offline Driver",
            approval_status=DriverProfile.ApprovalStatus.APPROVED,
            operational_status=DriverProfile.OperationalStatus.OFFLINE,
        )
        self.client.force_authenticate(user=self.sales)
        second = self.client.post(
            "/api/v1/orders/",
            {
                "customer_id": self.customer.id,
                "restaurant_id": self.restaurant.id,
                "items": [{"menu_item_id": self.menu_item.id, "quantity": 1}],
                "delivery_address": {
                    "receiver_name": "Amina",
                    "phone": "+212600000001",
                    "address_line": "Medina",
                },
            },
            format="json",
        )
        order2 = second.json()["id"]
        res = self.client.post(
            f"/api/v1/orders/{order2}/assign-driver/",
            {"driver_id": offline.id},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
