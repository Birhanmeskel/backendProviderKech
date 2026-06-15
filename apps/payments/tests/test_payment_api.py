import hashlib
import hmac
import json
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.orders.models import Order
from apps.payments.models import Payment
from apps.restaurants.models import MenuCategory, MenuItem, Restaurant
from core.models import User

CHAPA_TEST_SETTINGS = {
    "CHAPA_MOCK_MODE": True,
    "CHAPA_SECRET_KEY": "CHASECK_TEST-mock",
    "CHAPA_WEBHOOK_SECRET": "webhook-test-secret",
    "CHAPA_CALLBACK_URL": "http://127.0.0.1:8000/api/v1/payments/callback/chapa/",
    "CHAPA_RETURN_URL": "kechdelivery://payment/return",
    "CHAPA_CURRENCY": "ETB",
}


@override_settings(**CHAPA_TEST_SETTINGS)
class PaymentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            phone="+72000000010",
            password="ComplexPass1!",
            role=User.Role.CUSTOMER,
        )
        self.other = User.objects.create_user(
            phone="+72000000011",
            password="ComplexPass1!",
            role=User.Role.CUSTOMER,
        )
        self.admin = User.objects.create_user(
            phone="+72000000012",
            password="ComplexPass1!",
            role=User.Role.ADMIN,
        )
        self.restaurant = Restaurant.objects.create(
            name="Pay Bistro",
            latitude=Decimal("9.03"),
            longitude=Decimal("38.74"),
            is_active=True,
        )
        category = MenuCategory.objects.create(restaurant=self.restaurant, name="Main")
        self.menu_item = MenuItem.objects.create(
            restaurant=self.restaurant,
            category=category,
            name="Injera",
            price=Decimal("100.00"),
            is_available=True,
        )
        self.order = Order.objects.create(
            reference="KD-1001",
            customer=self.customer,
            restaurant=self.restaurant,
            status=Order.Status.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
            subtotal=Decimal("100.00"),
            delivery_fee=Decimal("25.00"),
            total_amount=Decimal("125.00"),
            delivery_address={
                "receiver_name": "Test User",
                "phone": "0912345678",
                "address_line": "Addis Ababa",
            },
        )

    def test_chapa_customer_email_and_return_http_url(self):
        from apps.payments.services.payment import _customer_email, _return_http_url

        email = _customer_email(self.customer, self.order)
        self.assertTrue(email.endswith("@ethionet.et"))
        self.assertNotIn(".local", email)
        self.assertNotIn("kechdelivery.app", email)

        from apps.payments.services.payment import _chapa_phone_number

        phone = _chapa_phone_number(self.customer, self.order)
        self.assertRegex(phone, r"^0[79]\d{8}$")

        return_url = _return_http_url(self.order.id, "KCH-1-testref")
        self.assertTrue(return_url.startswith("http"))
        self.assertIn("return/chapa", return_url)
        self.assertIn("tx_ref=", return_url)

    def test_initialize_payment(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.post("/api/v1/payments/init/", {"order_id": self.order.id}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("checkout_url", res.json())
        self.assertTrue(res.json()["checkout_url"])
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.amount, self.order.total_amount)

    def test_initialize_rejects_other_customer(self):
        self.client.force_authenticate(user=self.other)
        res = self.client.post("/api/v1/payments/init/", {"order_id": self.order.id}, format="json")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_verify_payment_success(self):
        self.client.force_authenticate(user=self.customer)
        init = self.client.post("/api/v1/payments/init/", {"order_id": self.order.id}, format="json")
        tx_ref = init.json()["chapa_tx_ref"]

        verify = self.client.post("/api/v1/payments/verify/", {"tx_ref": tx_ref}, format="json")
        self.assertEqual(verify.status_code, status.HTTP_200_OK)
        self.assertEqual(verify.json()["status"], Payment.Status.SUCCESS)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)

    def test_verify_idempotent(self):
        self.client.force_authenticate(user=self.customer)
        init = self.client.post("/api/v1/payments/init/", {"order_id": self.order.id}, format="json")
        tx_ref = init.json()["chapa_tx_ref"]
        self.client.post("/api/v1/payments/verify/", {"tx_ref": tx_ref}, format="json")
        again = self.client.post("/api/v1/payments/verify/", {"tx_ref": tx_ref}, format="json")
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(Payment.objects.filter(chapa_tx_ref=tx_ref, status=Payment.Status.SUCCESS).count(), 1)

    def test_confirm_payment_via_order_endpoint(self):
        self.client.force_authenticate(user=self.customer)
        self.client.post("/api/v1/payments/init/", {"order_id": self.order.id}, format="json")
        confirm = self.client.post(f"/api/v1/orders/{self.order.id}/confirm-payment/")
        self.assertEqual(confirm.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm.json()["payment_status"], Order.PaymentStatus.PAID)

    def test_webhook_verifies_with_signature(self):
        self.client.force_authenticate(user=self.customer)
        init = self.client.post("/api/v1/payments/init/", {"order_id": self.order.id}, format="json")
        tx_ref = init.json()["chapa_tx_ref"]
        payload = {"event": "charge.success", "status": "success", "tx_ref": tx_ref, "amount": "125.00"}
        body = json.dumps(payload).encode("utf-8")
        sig = hmac.new(
            CHAPA_TEST_SETTINGS["CHAPA_WEBHOOK_SECRET"].encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        self.client.force_authenticate(user=None)
        res = self.client.post(
            "/api/v1/payments/webhook/chapa/",
            data=body,
            content_type="application/json",
            HTTP_X_CHAPA_SIGNATURE=sig,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    def test_webhook_rejects_bad_signature(self):
        payload = {"event": "charge.success", "tx_ref": "fake"}
        res = self.client.post(
            "/api/v1/payments/webhook/chapa/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CHAPA_SIGNATURE="invalid",
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_lists_payments(self):
        self.client.force_authenticate(user=self.customer)
        self.client.post("/api/v1/payments/init/", {"order_id": self.order.id}, format="json")

        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/payments/?status=pending")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res.json()["count"], 1)

    def test_admin_lists_payment_with_blank_checkout_url(self):
        Payment.objects.create(
            order=self.order,
            customer=self.customer,
            amount=Decimal("125.00"),
            currency="ETB",
            chapa_tx_ref="KCH-blank-url-test",
            checkout_url="",
            status=Payment.Status.PENDING,
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/payments/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        row = next(r for r in res.json()["results"] if r["chapa_tx_ref"] == "KCH-blank-url-test")
        self.assertEqual(row["checkout_url"], "")

    def test_initialize_rejects_paid_order(self):
        self.order.payment_status = Order.PaymentStatus.PAID
        self.order.save(update_fields=["payment_status"])
        self.client.force_authenticate(user=self.customer)
        res = self.client.post("/api/v1/payments/init/", {"order_id": self.order.id}, format="json")
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
