from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.restaurants.models import MenuCategory, MenuItem, Restaurant
from core.models import User


class RestaurantApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            phone="+71000000001",
            password="ComplexPass1!",
            role=User.Role.ADMIN,
        )
        self.sales = User.objects.create_user(
            phone="+71000000002",
            password="ComplexPass1!",
            role=User.Role.SALES,
        )
        self.customer = User.objects.create_user(
            phone="+71000000003",
            password="ComplexPass1!",
            role=User.Role.CUSTOMER,
        )
        self.driver = User.objects.create_user(
            phone="+71000000004",
            password="ComplexPass1!",
            role=User.Role.DRIVER,
        )

    def _create_restaurant(self, name: str = "Café Arabe", *, is_active: bool = True) -> Restaurant:
        return Restaurant.objects.create(
            name=name,
            description="Test",
            phone="+212600000000",
            address_text="Marrakech",
            latitude=Decimal("31.629500"),
            longitude=Decimal("-7.981100"),
            opening_hours="09:00–22:00",
            is_active=is_active,
        )

    def test_public_list_active_only(self):
        self._create_restaurant("Active One", is_active=True)
        self._create_restaurant("Hidden", is_active=False)

        res = self.client.get("/api/v1/restaurants/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        names = [r["name"] for r in res.json()]
        self.assertIn("Active One", names)
        self.assertNotIn("Hidden", names)

    def _jpeg_upload(self, name: str = "logo.jpg") -> SimpleUploadedFile:
        buf = BytesIO()
        Image.new("RGB", (32, 32), color="red").save(buf, format="JPEG")
        buf.seek(0)
        return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")

    def test_admin_create_with_logo_and_cover(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/v1/restaurants/",
            {
                "name": "Image Bistro",
                "latitude": "9.030000",
                "longitude": "38.740000",
                "is_active": "true",
                "logo": self._jpeg_upload("logo.jpg"),
                "cover_image": self._jpeg_upload("cover.jpg"),
            },
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.content)
        body = res.json()
        self.assertTrue(body["logo_url"])
        self.assertTrue(body["cover_image_url"])

    def test_admin_can_create_and_update(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/v1/restaurants/",
            {
                "name": "Le Jardin",
                "latitude": "31.620000",
                "longitude": "-7.990000",
                "opening_hours": "10:00–23:00",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        rid = res.json()["id"]

        patch = self.client.patch(
            f"/api/v1/restaurants/{rid}/",
            {"description": "Garden dining"},
            format="json",
        )
        self.assertEqual(patch.status_code, status.HTTP_200_OK)
        self.assertEqual(patch.json()["description"], "Garden dining")

    def test_sales_cannot_create(self):
        self.client.force_authenticate(user=self.sales)
        res = self.client.post(
            "/api/v1/restaurants/",
            {"name": "X", "latitude": "31.6", "longitude": "-7.9"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_menu_nested_payload(self):
        restaurant = self._create_restaurant("Nomad")
        category = MenuCategory.objects.create(restaurant=restaurant, name="Mains", sort_order=1)
        MenuItem.objects.create(
            restaurant=restaurant,
            category=category,
            name="Tagine",
            price=Decimal("85.00"),
            is_available=True,
        )
        MenuItem.objects.create(
            restaurant=restaurant,
            category=category,
            name="Unavailable",
            price=Decimal("10.00"),
            is_available=False,
        )

        res = self.client.get(f"/api/v1/restaurants/{restaurant.id}/menu/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = res.json()
        self.assertEqual(body["restaurant_name"], "Nomad")
        self.assertEqual(len(body["categories"]), 1)
        self.assertEqual(len(body["categories"][0]["items"]), 1)
        self.assertEqual(body["categories"][0]["items"][0]["name"], "Tagine")

    def test_admin_menu_crud(self):
        restaurant = self._create_restaurant("Menu Test")
        self.client.force_authenticate(user=self.admin)

        cat = self.client.post(
            f"/api/v1/restaurants/{restaurant.id}/categories/",
            {"name": "Starters", "sort_order": 1},
            format="json",
        )
        self.assertEqual(cat.status_code, status.HTTP_201_CREATED)
        cat_id = cat.json()["id"]

        item = self.client.post(
            f"/api/v1/restaurants/{restaurant.id}/menu-items/",
            {
                "category_id": cat_id,
                "name": "Harira",
                "price": "35.00",
                "description": "Soup",
            },
            format="json",
        )
        self.assertEqual(item.status_code, status.HTTP_201_CREATED)

    def test_driver_cannot_mutate_catalog(self):
        restaurant = self._create_restaurant("Driver Block")
        self.client.force_authenticate(user=self.driver)
        res = self.client.post(
            f"/api/v1/restaurants/{restaurant.id}/categories/",
            {"name": "Blocked"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_sales_can_read_staff_catalog(self):
        restaurant = self._create_restaurant("Sales Read", is_active=False)
        self.client.force_authenticate(user=self.sales)
        res = self.client.get("/api/v1/restaurants/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        names = [r["name"] for r in res.json()]
        self.assertIn("Sales Read", names)
