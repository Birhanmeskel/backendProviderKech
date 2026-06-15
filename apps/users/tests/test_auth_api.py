from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.drivers.models import DriverProfile
from apps.users.auth_policy import SUSPENDED_ACCOUNT_MESSAGE
from core.models import User


class AuthApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _obtain_token(self, phone: str, password: str):
        return self.client.post(
            "/api/v1/auth/token/",
            {"phone": phone, "password": password},
            format="json",
        )

    def test_health_and_ready(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json().get("status"), "ok")

        r2 = self.client.get("/ready")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(r2.json().get("status"), "ready")

    def test_customer_register_token_me(self):
        reg = self.client.post(
            "/api/v1/auth/register/customer",
            {
                "phone": "+10000000001",
                "password": "ComplexPass1!",
                "name": "Ada",
                "email": "ada@example.com",
            },
            format="json",
        )
        self.assertEqual(reg.status_code, status.HTTP_201_CREATED)

        bad = self._obtain_token("+10000000001", "wrong")
        self.assertIn(bad.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED))
        self.assertEqual(bad.json().get("detail"), "Invalid credentials.")

        pair = self._obtain_token("+10000000001", "ComplexPass1!")
        self.assertEqual(pair.status_code, status.HTTP_200_OK)
        body = pair.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)
        self.assertEqual(body.get("role"), "customer")
        self.assertEqual(body.get("user_id"), reg.json()["user_id"])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
        me = self.client.get("/api/v1/auth/me")
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.json()["phone"], "+10000000001")
        self.assertEqual(me.json()["profile"]["full_name"], "Ada")
        self.assertEqual(me.json()["profile"]["email"], "ada@example.com")

    def test_phone_normalization_duplicate_blocked(self):
        self.client.post(
            "/api/v1/auth/register/customer",
            {
                "phone": "+10000000005",
                "password": "ComplexPass1!",
                "name": "A",
                "email": "a@example.com",
            },
            format="json",
        )
        dup = self.client.post(
            "/api/v1/auth/register/customer",
            {
                "phone": "+10000000005",
                "password": "ComplexPass1!",
                "name": "B",
                "email": "b@example.com",
            },
            format="json",
        )
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(dup.json().get("phone"), ["A user with this phone number already exists."])

    def test_driver_pending_cannot_obtain_tokens(self):
        reg = self.client.post(
            "/api/v1/auth/register/driver",
            {
                "phone": "+20000000002",
                "password": "ComplexPass1!",
                "name": "Bob",
                "email": "bob@example.com",
                "vehicle_type": "sedan",
            },
            format="json",
        )
        self.assertEqual(reg.status_code, status.HTTP_201_CREATED)
        self.assertEqual(reg.json()["approval_status"], "pending")

        pair = self._obtain_token("+20000000002", "ComplexPass1!")
        self.assertIn(pair.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED))
        self.assertEqual(pair.json().get("detail"), "Invalid credentials.")

    def test_suspended_driver_cannot_obtain_tokens(self):
        self.client.post(
            "/api/v1/auth/register/driver",
            {
                "phone": "+20000000004",
                "password": "ComplexPass1!",
                "name": "Suspended",
                "email": "suspended@example.com",
                "vehicle_type": "sedan",
            },
            format="json",
        )
        user = User.objects.get(phone="+20000000004")
        dp = user.driver_profile
        dp.approval_status = DriverProfile.ApprovalStatus.APPROVED
        dp.save(update_fields=["approval_status"])
        dp.approval_status = DriverProfile.ApprovalStatus.SUSPENDED
        dp.suspension_reason = "Policy violation"
        dp.save(update_fields=["approval_status", "suspension_reason"])

        pair = self._obtain_token("+20000000004", "ComplexPass1!")
        self.assertIn(pair.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED))
        self.assertEqual(pair.json().get("detail"), SUSPENDED_ACCOUNT_MESSAGE)

    def test_driver_approved_token_refresh_logout(self):
        self.client.post(
            "/api/v1/auth/register/driver",
            {
                "phone": "+20000000003",
                "password": "ComplexPass1!",
                "name": "Cara",
                "email": "cara@example.com",
                "vehicle_type": "motorbike",
            },
            format="json",
        )
        user = User.objects.get(phone="+20000000003")
        dp = user.driver_profile
        dp.approval_status = DriverProfile.ApprovalStatus.APPROVED
        dp.save(update_fields=["approval_status"])

        pair = self._obtain_token("+20000000003", "ComplexPass1!")
        self.assertEqual(pair.status_code, status.HTTP_200_OK)
        refresh = pair.json()["refresh"]
        access = pair.json()["access"]

        ref = self.client.post(
            "/api/v1/auth/token/refresh/",
            {"refresh": refresh},
            format="json",
        )
        self.assertEqual(ref.status_code, status.HTTP_200_OK)
        self.assertIn("access", ref.json())

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        out = self.client.post("/api/v1/auth/logout", {"refresh": refresh}, format="json")
        self.assertEqual(out.status_code, status.HTTP_204_NO_CONTENT)

        ref2 = self.client.post(
            "/api/v1/auth/token/refresh/",
            {"refresh": refresh},
            format="json",
        )
        self.assertIn(
            ref2.status_code,
            (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED),
        )
        self.assertEqual(ref2.json().get("detail"), "Invalid credentials.")

    def test_staff_ops_check_role_gate(self):
        User.objects.create_user(
            phone="+30000000001",
            password="ComplexPass1!",
            role=User.Role.SALES,
        )
        pair = self._obtain_token("+30000000001", "ComplexPass1!")
        self.assertEqual(pair.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.json()['access']}")
        ok = self.client.get("/api/v1/auth/staff/ops-check")
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertTrue(ok.json().get("ok"))

        User.objects.create_user(
            phone="+30000000002",
            password="ComplexPass1!",
            role=User.Role.CUSTOMER,
        )
        pair_c = self._obtain_token("+30000000002", "ComplexPass1!")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair_c.json()['access']}")
        denied = self.client.get("/api/v1/auth/staff/ops-check")
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_sales_agent(self):
        admin = User.objects.create_user(
            phone="+40000000001",
            password="ComplexPass1!",
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=admin)

        res = self.client.post(
            "/api/v1/auth/create-sales-agent/",
            {
                "phone": "+40000000002",
                "password": "ComplexPass1!",
                "name": "Sara Kebede",
            },
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        body = res.json()
        self.assertEqual(body["role"], User.Role.SALES)
        self.assertEqual(body["phone"], "+40000000002")
        self.assertEqual(body["name"], "Sara Kebede")
        self.assertIn("user_id", body)
        self.assertNotIn("password", body)

        created = User.objects.get(id=body["user_id"])
        self.assertEqual(created.role, User.Role.SALES)
        self.assertTrue(created.check_password("ComplexPass1!"))
        self.assertEqual(created.sales_profile.full_name, "Sara Kebede")

    def test_non_admin_cannot_create_sales_agent(self):
        sales_user = User.objects.create_user(
            phone="+40000000003",
            password="ComplexPass1!",
            role=User.Role.SALES,
        )
        self.client.force_authenticate(user=sales_user)

        res = self.client.post(
            "/api/v1/auth/create-sales-agent/",
            {"phone": "+40000000004", "password": "ComplexPass1!"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_sales_agent_duplicate_phone_returns_specific_error(self):
        admin = User.objects.create_user(
            phone="+40000000005",
            password="ComplexPass1!",
            role=User.Role.ADMIN,
        )
        User.objects.create_user(
            phone="+40000000006",
            password="ComplexPass1!",
            role=User.Role.SALES,
        )
        self.client.force_authenticate(user=admin)

        res = self.client.post(
            "/api/v1/auth/create-sales-agent/",
            {"phone": "+40000000006", "password": "ComplexPass1!"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.json().get("phone"), ["User already exists."])

    def test_create_sales_agent_weak_password_returns_password_error(self):
        admin = User.objects.create_user(
            phone="+40000000007",
            password="ComplexPass1!",
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=admin)

        res = self.client.post(
            "/api/v1/auth/create-sales-agent/",
            {"phone": "+40000000008", "password": "123"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", res.json())

    def test_admin_can_list_users_newest_first(self):
        from apps.users.models import CustomerProfile

        admin = User.objects.create_user(
            phone="+50000000001",
            password="ComplexPass1!",
            role=User.Role.ADMIN,
        )
        older = User.objects.create_user(
            phone="+50000000002",
            password="ComplexPass1!",
            role=User.Role.CUSTOMER,
        )
        CustomerProfile.objects.create(user=older, full_name="Ada Customer")
        newer = User.objects.create_user(
            phone="+50000000003",
            password="ComplexPass1!",
            role=User.Role.SALES,
        )
        older.created_at = timezone.now() - timezone.timedelta(hours=1)
        older.save(update_fields=["created_at"])
        newer.created_at = timezone.now()
        newer.save(update_fields=["created_at"])
        self.client.force_authenticate(user=admin)

        res = self.client.get("/api/v1/auth/users/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = res.json()
        self.assertGreaterEqual(len(body), 3)
        ordered_ids = [item["user_id"] for item in body]
        self.assertIn(newer.id, ordered_ids)
        self.assertIn(older.id, ordered_ids)
        self.assertLess(ordered_ids.index(newer.id), ordered_ids.index(older.id))
        newer_payload = next(item for item in body if item["user_id"] == newer.id)
        self.assertEqual(newer_payload["status"], "active")
        self.assertIsNone(newer_payload["name"])
        older_payload = next(item for item in body if item["user_id"] == older.id)
        self.assertEqual(older_payload["name"], "Ada Customer")

        by_name = self.client.get("/api/v1/auth/users/?q=Ada")
        self.assertEqual(by_name.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item["user_id"] == older.id for item in by_name.json()))
        self.assertFalse(any(item["user_id"] == newer.id for item in by_name.json()))

    def test_admin_user_list_shows_suspended_driver_status(self):
        admin = User.objects.create_user(
            phone="+50000000020",
            password="ComplexPass1!",
            role=User.Role.ADMIN,
        )
        driver = User.objects.create_user(
            phone="+50000000021",
            password="ComplexPass1!",
            role=User.Role.DRIVER,
        )
        profile, _ = DriverProfile.objects.get_or_create(
            user=driver,
            defaults={"full_name": "Suspended Driver"},
        )
        profile.approval_status = DriverProfile.ApprovalStatus.SUSPENDED
        profile.suspension_reason = "Policy violation"
        profile.save(update_fields=["approval_status", "suspension_reason"])

        self.client.force_authenticate(user=admin)
        res = self.client.get("/api/v1/auth/users/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        payload = next(item for item in res.json() if item["user_id"] == driver.id)
        self.assertEqual(payload["status"], "suspended")

    def test_customer_with_pending_order_can_delete_account(self):
        from apps.orders.models import Order
        from apps.restaurants.models import MenuCategory, MenuItem, Restaurant
        from decimal import Decimal

        reg = self.client.post(
            "/api/v1/auth/register/customer",
            {"phone": "+10000000051", "password": "ComplexPass1!", "name": "Pending Cart"},
            format="json",
        )
        self.assertEqual(reg.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(phone="+10000000051")
        rest = Restaurant.objects.create(name="R2", latitude=1, longitude=1, is_active=True)
        cat = MenuCategory.objects.create(restaurant=rest, name="C")
        MenuItem.objects.create(
            restaurant=rest,
            category=cat,
            name="Item",
            price=Decimal("10"),
            is_available=True,
        )
        Order.objects.create(
            reference="KD-PEND",
            customer=user,
            restaurant=rest,
            status=Order.Status.PENDING,
            subtotal=Decimal("10"),
            delivery_fee=Decimal("5"),
            total_amount=Decimal("15"),
            delivery_address={
                "receiver_name": "A",
                "phone": "+10000000051",
                "address_line": "Line",
            },
        )
        pair = self._obtain_token("+10000000051", "ComplexPass1!")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.json()['access']}")
        res = self.client.post(
            "/api/v1/auth/me/delete",
            {"refresh": pair.json()["refresh"]},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(User.objects.get(phone="+10000000051").is_active)

    def test_customer_can_delete_own_account(self):
        reg = self.client.post(
            "/api/v1/auth/register/customer",
            {
                "phone": "+10000000050",
                "password": "ComplexPass1!",
                "name": "Delete Me",
                "email": "delete@example.com",
            },
            format="json",
        )
        self.assertEqual(reg.status_code, status.HTTP_201_CREATED)
        pair = self._obtain_token("+10000000050", "ComplexPass1!")
        refresh = pair.json()["refresh"]
        access = pair.json()["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        res = self.client.post("/api/v1/auth/me/delete", {"refresh": refresh}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        user = User.objects.get(phone="+10000000050")
        self.assertFalse(user.is_active)

        blocked = self._obtain_token("+10000000050", "ComplexPass1!")
        self.assertIn(blocked.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED))

    def test_driver_can_delete_own_account(self):
        from apps.drivers.services.approval import approve_driver

        reg = self.client.post(
            "/api/v1/auth/register/driver",
            {
                "phone": "+20000000050",
                "password": "ComplexPass1!",
                "name": "Driver Delete",
                "email": "del@example.com",
                "vehicle_type": "sedan",
            },
            format="json",
        )
        self.assertEqual(reg.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(phone="+20000000050")
        admin = User.objects.create_user(
            phone="+60000000099",
            password="ComplexPass1!",
            role=User.Role.ADMIN,
        )
        approve_driver(user_id=user.id, admin=admin)
        pair = self._obtain_token("+20000000050", "ComplexPass1!")
        self.assertEqual(pair.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.json()['access']}")
        res = self.client.post(
            "/api/v1/auth/me/delete/",
            {"refresh": pair.json()["refresh"]},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(User.objects.get(phone="+20000000050").is_active)

    def test_non_admin_cannot_list_users(self):
        customer = User.objects.create_user(
            phone="+50000000004",
            password="ComplexPass1!",
            role=User.Role.CUSTOMER,
        )
        self.client.force_authenticate(user=customer)
        res = self.client.get("/api/v1/auth/users/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_sales_can_search_customers_by_phone_and_name(self):
        reg = self.client.post(
            "/api/v1/auth/register/customer",
            {
                "phone": "+19998887777",
                "password": "ComplexPass1!",
                "name": "Zara Customer",
                "email": "zara@example.com",
            },
            format="json",
        )
        self.assertEqual(reg.status_code, status.HTTP_201_CREATED)
        customer_id = reg.json()["user_id"]

        sales = User.objects.create_user(
            phone="+50000000010",
            password="ComplexPass1!",
            role=User.Role.SALES,
        )
        self.client.force_authenticate(user=sales)

        by_phone = self.client.get("/api/v1/auth/customers/search/?q=998887")
        self.assertEqual(by_phone.status_code, status.HTTP_200_OK)
        results = by_phone.json()["results"]
        self.assertTrue(any(r["id"] == customer_id for r in results))

        by_name = self.client.get("/api/v1/auth/customers/search/?q=Zara")
        self.assertEqual(by_name.status_code, status.HTTP_200_OK)
        self.assertTrue(any(r["name"] == "Zara Customer" for r in by_name.json()["results"]))

    def test_customer_cannot_search_customers(self):
        reg = self.client.post(
            "/api/v1/auth/register/customer",
            {
                "phone": "+19998887778",
                "password": "ComplexPass1!",
                "name": "Bob",
                "email": "bob@example.com",
            },
            format="json",
        )
        pair = self._obtain_token("+19998887778", "ComplexPass1!")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.json()['access']}")
        res = self.client.get("/api/v1/auth/customers/search/?q=Bob")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
