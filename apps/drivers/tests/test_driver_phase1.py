from django.test import TestCase
from rest_framework import status
from rest_framework.request import Request as DRFRequest
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.drivers.models import DriverProfile
from apps.drivers.services.approval import approve_driver, suspend_driver
from apps.users.permissions import IsApprovedDriver
from core.models import User


class DriverApprovalApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            phone="+60000000001",
            password="ComplexPass1!",
            role=User.Role.ADMIN,
        )
        self.sales = User.objects.create_user(
            phone="+60000000002",
            password="ComplexPass1!",
            role=User.Role.SALES,
        )
        self.customer = User.objects.create_user(
            phone="+60000000003",
            password="ComplexPass1!",
            role=User.Role.CUSTOMER,
        )

    def _register_driver(self, phone: str, name: str = "Test Driver") -> dict:
        res = self.client.post(
            "/api/v1/auth/register/driver",
            {
                "phone": phone,
                "password": "ComplexPass1!",
                "name": name,
                "email": "driver@example.com",
                "vehicle_type": "sedan",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        return res.json()

    def _admin_auth(self):
        self.client.force_authenticate(user=self.admin)

    def test_admin_can_list_pending_drivers_newest_first(self):
        first = self._register_driver("+61000000001", "First")
        second = self._register_driver("+61000000002", "Second")
        self._admin_auth()

        res = self.client.get("/api/v1/admin/drivers/pending/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = res.json()
        self.assertEqual(len(body), 2)
        self.assertEqual(body[0]["user_id"], second["id"])
        self.assertEqual(body[1]["user_id"], first["id"])
        self.assertEqual(body[0]["approval_status"], "pending")
        self.assertIn("phone", body[0])
        self.assertIn("full_name", body[0])
        self.assertIn("created_at", body[0])

    def test_admin_can_approve_driver(self):
        reg = self._register_driver("+61000000010")
        self._admin_auth()

        res = self.client.post(f"/api/v1/admin/drivers/{reg['id']}/approve/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["approval_status"], "approved")
        self.assertEqual(res.json()["driver_id"], reg["id"])
        self.assertIn("message", res.json())

        profile = DriverProfile.objects.get(user_id=reg["id"])
        self.assertEqual(profile.approval_status, DriverProfile.ApprovalStatus.APPROVED)
        self.assertIsNotNone(profile.approved_at)
        self.assertEqual(profile.approved_by_id, self.admin.id)

    def test_approve_already_approved_returns_409(self):
        reg = self._register_driver("+61000000011")
        self._admin_auth()
        self.client.post(f"/api/v1/admin/drivers/{reg['id']}/approve/")
        again = self.client.post(f"/api/v1/admin/drivers/{reg['id']}/approve/")
        self.assertEqual(again.status_code, status.HTTP_409_CONFLICT)

    def test_sales_cannot_approve(self):
        reg = self._register_driver("+61000000012")
        self.client.force_authenticate(user=self.sales)
        res = self.client.post(f"/api/v1/admin/drivers/{reg['id']}/approve/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_cannot_approve(self):
        reg = self._register_driver("+61000000013")
        self.client.force_authenticate(user=self.customer)
        res = self.client.post(f"/api/v1/admin/drivers/{reg['id']}/approve/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_approve_invalid_driver_id_returns_404(self):
        self._admin_auth()
        res = self.client.post("/api/v1/admin/drivers/999999/approve/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_reject_pending_driver(self):
        reg = self._register_driver("+61000000020")
        self._admin_auth()
        res = self.client.post(
            f"/api/v1/admin/drivers/{reg['id']}/reject/",
            {"rejection_reason": "Invalid documents"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        profile = DriverProfile.objects.get(user_id=reg["id"])
        self.assertEqual(profile.approval_status, DriverProfile.ApprovalStatus.REJECTED)
        self.assertEqual(profile.rejection_reason, "Invalid documents")
        self.assertEqual(profile.reviewed_by_id, self.admin.id)

    def test_admin_can_suspend_approved_driver(self):
        reg = self._register_driver("+61000000030")
        user = User.objects.get(id=reg["id"])
        approve_driver(user_id=user.id, admin=self.admin)
        self._admin_auth()
        res = self.client.post(
            f"/api/v1/admin/drivers/{reg['id']}/suspend/",
            {"suspension_reason": "Policy violation"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        profile = DriverProfile.objects.get(user_id=reg["id"])
        self.assertEqual(profile.approval_status, DriverProfile.ApprovalStatus.SUSPENDED)
        self.assertEqual(profile.suspension_reason, "Policy violation")

    def test_admin_can_list_suspended_drivers(self):
        reg = self._register_driver("+61000000031")
        user = User.objects.get(id=reg["id"])
        approve_driver(user_id=user.id, admin=self.admin)
        suspend_driver(
            user_id=user.id,
            admin=self.admin,
            suspension_reason="Policy violation",
        )
        self._admin_auth()
        res = self.client.get("/api/v1/admin/drivers/suspended/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()), 1)
        self.assertEqual(res.json()[0]["user_id"], reg["id"])
        self.assertEqual(res.json()[0]["suspension_reason"], "Policy violation")

    def test_admin_can_list_driver_documents(self):
        from apps.drivers.models import DriverDocument
        from django.core.files.uploadedfile import SimpleUploadedFile

        reg = self._register_driver("+61000000033")
        user = User.objects.get(id=reg["id"])
        DriverDocument.objects.create(
            user=user,
            document_type=DriverDocument.DocumentType.LICENSE,
            file=SimpleUploadedFile("license.jpg", b"fake-image", content_type="image/jpeg"),
        )
        self._admin_auth()
        res = self.client.get(f"/api/v1/admin/drivers/{reg['id']}/documents/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()["documents"]), 1)
        self.assertIn("file_url", res.json()["documents"][0])

    def test_admin_can_reactivate_suspended_driver(self):
        reg = self._register_driver("+61000000032")
        user = User.objects.get(id=reg["id"])
        approve_driver(user_id=user.id, admin=self.admin)
        suspend_driver(
            user_id=user.id,
            admin=self.admin,
            suspension_reason="Temporary hold",
        )
        self._admin_auth()
        res = self.client.post(f"/api/v1/admin/drivers/{reg['id']}/reactivate/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["approval_status"], "approved")
        profile = DriverProfile.objects.get(user_id=reg["id"])
        self.assertEqual(profile.approval_status, DriverProfile.ApprovalStatus.APPROVED)
        self.assertIsNone(profile.suspended_at)
        self.assertEqual(profile.suspension_reason, "")
        self.assertEqual(profile.operational_status, DriverProfile.OperationalStatus.OFFLINE)


class IsApprovedDriverPermissionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = IsApprovedDriver()

    def _driver_with_status(self, status_value: str) -> User:
        suffix = User.objects.count() + 1
        user = User.objects.create_user(
            phone=f"+620{suffix:08d}",
            password="ComplexPass1!",
            role=User.Role.DRIVER,
        )
        profile, _ = DriverProfile.objects.get_or_create(
            user=user,
            defaults={"full_name": "Perm Test"},
        )
        profile.approval_status = status_value
        profile.save(update_fields=["approval_status"])
        return user

    def _drf_request(self, user: User) -> DRFRequest:
        wsgi = self.factory.get("/")
        force_authenticate(wsgi, user=user)
        return DRFRequest(wsgi)

    def test_approved_driver_passes(self):
        user = self._driver_with_status(DriverProfile.ApprovalStatus.APPROVED)
        self.assertTrue(self.permission.has_permission(self._drf_request(user), None))

    def test_pending_driver_denied(self):
        user = self._driver_with_status(DriverProfile.ApprovalStatus.PENDING)
        self.assertFalse(self.permission.has_permission(self._drf_request(user), None))

    def test_suspended_driver_denied(self):
        user = self._driver_with_status(DriverProfile.ApprovalStatus.SUSPENDED)
        self.assertFalse(self.permission.has_permission(self._drf_request(user), None))


class SafeJWTAuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            phone="+63000000001",
            password="ComplexPass1!",
            role=User.Role.ADMIN,
        )

    def _register_and_approve_driver(self, phone: str) -> User:
        reg = self.client.post(
            "/api/v1/auth/register/driver",
            {
                "phone": phone,
                "password": "ComplexPass1!",
                "name": "Fleet",
                "email": "fleet@example.com",
                "vehicle_type": "sedan",
            },
            format="json",
        )
        user = User.objects.get(id=reg.json()["id"])
        approve_driver(user_id=user.id, admin=self.admin)
        return user

    def _token_for(self, phone: str) -> str:
        res = self.client.post(
            "/api/v1/auth/token/",
            {"phone": phone, "password": "ComplexPass1!"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return res.json()["access"]

    def test_suspended_driver_token_blocked_immediately(self):
        phone = "+63000000010"
        self._register_and_approve_driver(phone)
        access = self._token_for(phone)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        me = self.client.get("/api/v1/auth/me")
        self.assertEqual(me.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.admin)
        self.client.post(
            f"/api/v1/admin/drivers/{User.objects.get(phone=phone).id}/suspend/",
            {"suspension_reason": "Fraud"},
            format="json",
        )

        # Clear admin session so the next request uses only the driver's JWT.
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        blocked = self.client.get("/api/v1/auth/me")
        self.assertEqual(blocked.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejected_driver_cannot_obtain_token(self):
        reg = self.client.post(
            "/api/v1/auth/register/driver",
            {
                "phone": "+63000000020",
                "password": "ComplexPass1!",
                "name": "X",
                "email": "x@example.com",
                "vehicle_type": "sedan",
            },
            format="json",
        )
        user = User.objects.get(id=reg.json()["id"])
        profile = user.driver_profile
        profile.approval_status = DriverProfile.ApprovalStatus.REJECTED
        profile.save(update_fields=["approval_status"])

        pair = self.client.post(
            "/api/v1/auth/token/",
            {"phone": "+63000000020", "password": "ComplexPass1!"},
            format="json",
        )
        self.assertIn(pair.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED))

    def test_inactive_user_token_blocked(self):
        phone = "+63000000030"
        self._register_and_approve_driver(phone)
        access = self._token_for(phone)
        user = User.objects.get(phone=phone)
        user.is_active = False
        user.save(update_fields=["is_active"])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        blocked = self.client.get("/api/v1/auth/me")
        self.assertEqual(blocked.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_auth_unaffected_by_safe_jwt(self):
        reg = self.client.post(
            "/api/v1/auth/register/customer",
            {
                "phone": "+63000000040",
                "password": "ComplexPass1!",
                "name": "Cust",
                "email": "cust@example.com",
            },
            format="json",
        )
        access = self._token_for("+63000000040")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        me = self.client.get("/api/v1/auth/me")
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.json()["role"], "customer")
        self.assertEqual(me.json()["id"], reg.json()["user_id"])


class DriverStatusApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_authenticated_driver_gets_own_status(self):
        reg = self.client.post(
            "/api/v1/auth/register/driver",
            {
                "phone": "+64000000001",
                "password": "ComplexPass1!",
                "name": "Status",
                "email": "status@example.com",
                "vehicle_type": "sedan",
            },
            format="json",
        )
        user = User.objects.get(id=reg.json()["id"])
        self.client.force_authenticate(user=user)

        res = self.client.get("/api/v1/drivers/me/status/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["approval_status"], "pending")

    def test_unauthenticated_denied(self):
        res = self.client.get("/api/v1/drivers/me/status/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_cannot_access_driver_status(self):
        customer = User.objects.create_user(
            phone="+64000000002",
            password="ComplexPass1!",
            role=User.Role.CUSTOMER,
        )
        self.client.force_authenticate(user=customer)
        res = self.client.get("/api/v1/drivers/me/status/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
