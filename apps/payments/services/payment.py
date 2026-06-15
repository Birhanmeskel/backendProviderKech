"""Payment business logic — init, verify, webhook (Chapa)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import uuid
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.services.order import OrderServiceError, mark_order_paid_from_payment
from apps.payments.models import Payment
from apps.payments.services import chapa_client
from apps.payments.services.chapa_client import ChapaClientError, ChapaVerifyResult
from core.models import User

logger = logging.getLogger("kech.payments")


class PaymentServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _customer_email(user: User, order: Order) -> str:
    """
    Synthetic checkout email — Chapa validates the domain (rejects kechdelivery.app).
    Use CHAPA_CUSTOMER_EMAIL_DOMAIN for a Chapa-accepted domain (default: ethionet.et).
    """
    domain = (
        getattr(settings, "CHAPA_CUSTOMER_EMAIL_DOMAIN", "ethionet.et") or "ethionet.et"
    ).strip().lstrip("@")
    addr = order.delivery_address or {}
    phone = addr.get("phone") or user.phone or "customer"
    digits = re.sub(r"\D", "", str(phone)) or "900000000"
    if digits.startswith("251") and len(digits) >= 12:
        digits = digits[3:12]
    elif digits.startswith("0") and len(digits) >= 10:
        digits = digits[1:10]
    elif len(digits) > 9:
        digits = digits[-9:]
    return f"customer{digits}@{domain}"


def _chapa_phone_number(user: User, order: Order) -> str:
    """Chapa expects Ethiopian mobile as 09xxxxxxxx or 07xxxxxxxx (10 digits)."""
    addr = order.delivery_address or {}
    raw = addr.get("phone") or user.phone or ""
    digits = re.sub(r"\D", "", str(raw))
    if digits.startswith("251") and len(digits) >= 12:
        local = digits[3:12]
    elif digits.startswith("0") and len(digits) >= 10:
        return digits[:10]
    elif len(digits) == 9 and digits[0] in "97":
        local = digits
    else:
        local = digits[-9:] if len(digits) >= 9 else "900000000"
    return f"0{local}" if len(local) == 9 else local[:10]


def _chapa_error_message(exc: ChapaClientError) -> str:
    payload = exc.payload
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, dict):
            parts: list[str] = []
            for field, errors in message.items():
                if isinstance(errors, list):
                    parts.append(f"{field}: {', '.join(str(item) for item in errors)}")
                else:
                    parts.append(f"{field}: {errors}")
            if parts:
                return "Chapa rejected the payment request. " + "; ".join(parts)
        if isinstance(message, str) and message.strip():
            return message.strip()
    if exc.message and not str(exc.message).startswith("{"):
        return str(exc.message)
    return "Chapa payment initialization failed."


def _customer_names(order: Order) -> tuple[str, str]:
    addr = order.delivery_address or {}
    full = (addr.get("receiver_name") or "Customer").strip()
    parts = full.split(None, 1)
    first = parts[0] if parts else "Customer"
    last = parts[1] if len(parts) > 1 else "User"
    return first, last


def _format_amount(amount: Decimal) -> str:
    return f"{amount.quantize(Decimal('0.01'))}"


def _generate_tx_ref(order_id: int) -> str:
    return f"KCH-{order_id}-{uuid.uuid4().hex[:12]}"


def _callback_url(order_id: int, tx_ref: str) -> str:
    base = getattr(settings, "CHAPA_CALLBACK_URL", "").rstrip("/")
    if not base:
        raise PaymentServiceError("CHAPA_CALLBACK_URL is not configured.", status_code=503)
    return f"{base}?order_id={order_id}&tx_ref={tx_ref}"


def _return_http_url(order_id: int, tx_ref: str) -> str:
    """HTTPS return URL sent to Chapa (must be http/https, not a mobile deep link)."""
    base = getattr(settings, "CHAPA_RETURN_HTTP_URL", "").strip().rstrip("/")
    if not base:
        callback = getattr(settings, "CHAPA_CALLBACK_URL", "")
        if "callback/chapa" in callback:
            base = callback.replace("/callback/chapa/", "/return/chapa/").rstrip("/")
        else:
            public_base = getattr(settings, "CHAPA_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip(
                "/"
            )
            base = f"{public_base}/api/v1/payments/return/chapa"
    if not base.startswith(("http://", "https://")):
        raise PaymentServiceError(
            "CHAPA_RETURN_HTTP_URL must be a valid http(s) URL for Chapa checkout.",
            status_code=503,
        )
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}order_id={order_id}&tx_ref={tx_ref}"


def _app_return_url(order_id: int, tx_ref: str) -> str:
    """Deep link opened by the mobile app after hosted checkout completes."""
    base = getattr(settings, "CHAPA_APP_RETURN_URL", "kechdelivery://payment/return").rstrip("/")
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}order_id={order_id}&tx_ref={tx_ref}"


@transaction.atomic
def initialize_payment(*, order: Order, customer: User) -> Payment:
    if customer.role != User.Role.CUSTOMER:
        raise PaymentServiceError("Only customers can initialize payments.", status_code=403)
    if order.customer_id != customer.pk:
        raise PaymentServiceError("Not allowed for this order.", status_code=403)
    if order.payment_status == Order.PaymentStatus.PAID:
        raise PaymentServiceError("Order is already paid.", status_code=409)
    if order.status == Order.Status.CANCELLED:
        raise PaymentServiceError("Cancelled orders cannot be paid.", status_code=409)
    if order.total_amount <= 0:
        raise PaymentServiceError("Invalid order amount.", status_code=400)

    existing = (
        Payment.objects.select_for_update()
        .filter(order=order, status=Payment.Status.PENDING)
        .exclude(checkout_url="")
        .order_by("-created_at")
        .first()
    )
    if existing and existing.checkout_url:
        return existing

    currency = getattr(settings, "CHAPA_CURRENCY", "ETB")
    tx_ref = _generate_tx_ref(order.pk)
    amount_str = _format_amount(order.total_amount)
    first_name, last_name = _customer_names(order)
    phone = _chapa_phone_number(customer, order)

    payment = Payment.objects.create(
        order=order,
        customer=customer,
        amount=order.total_amount,
        currency=currency,
        chapa_tx_ref=tx_ref,
        status=Payment.Status.PENDING,
    )

    try:
        init_result = chapa_client.initialize_transaction(
            amount=amount_str,
            currency=currency,
            email=_customer_email(customer, order),
            first_name=first_name,
            last_name=last_name,
            phone_number=phone,
            tx_ref=tx_ref,
            callback_url=_callback_url(order.pk, tx_ref),
            return_url=_return_http_url(order.pk, tx_ref),
            customization={
                "title": "Kech Delivery",
                "description": f"Order {order.reference}",
            },
            meta={"order_id": order.pk, "order_reference": order.reference},
        )
    except ChapaClientError as exc:
        payment.status = Payment.Status.FAILED
        payment.raw_initialize_response = exc.payload if isinstance(exc.payload, dict) else {"error": exc.message}
        payment.save(update_fields=["status", "raw_initialize_response", "updated_at"])
        raise PaymentServiceError(_chapa_error_message(exc), status_code=502) from exc

    payment.checkout_url = init_result.checkout_url
    payment.raw_initialize_response = init_result.raw
    payment.save(update_fields=["checkout_url", "raw_initialize_response", "updated_at"])
    logger.info("Payment initialized order=%s tx_ref=%s", order.pk, tx_ref)
    return payment


def _apply_verified_payment(payment: Payment, verify: ChapaVerifyResult) -> Payment:
    payment.raw_verify_response = verify.raw
    payment.chapa_reference = verify.chapa_reference or payment.chapa_reference
    payment.payment_method = verify.payment_method or payment.payment_method

    if verify.status == "success":
        if verify.amount is not None and not getattr(settings, "CHAPA_MOCK_MODE", False):
            verified_amount = Decimal(verify.amount)
            if verified_amount != payment.amount:
                payment.status = Payment.Status.FAILED
                payment.save(update_fields=["status", "raw_verify_response", "updated_at"])
                raise PaymentServiceError(
                    "Verified amount does not match order total.",
                    status_code=409,
                )
        if payment.status == Payment.Status.SUCCESS:
            return payment
        payment.status = Payment.Status.SUCCESS
        payment.paid_at = timezone.now()
        payment.save(
            update_fields=[
                "status",
                "paid_at",
                "chapa_reference",
                "payment_method",
                "raw_verify_response",
                "updated_at",
            ]
        )
        mark_order_paid_from_payment(payment.order)
        logger.info("Payment verified success tx_ref=%s order=%s", payment.chapa_tx_ref, payment.order_id)
        return payment

    if verify.status in {"failed", "cancelled"}:
        payment.status = (
            Payment.Status.CANCELLED if verify.status == "cancelled" else Payment.Status.FAILED
        )
        payment.save(update_fields=["status", "raw_verify_response", "updated_at"])
        if payment.order.payment_status == Order.PaymentStatus.PENDING:
            payment.order.payment_status = Order.PaymentStatus.FAILED
            payment.order.save(update_fields=["payment_status", "updated_at"])
        return payment

    payment.save(update_fields=["raw_verify_response", "updated_at"])
    return payment


@transaction.atomic
def verify_payment_by_tx_ref(*, tx_ref: str, customer: User | None = None) -> Payment:
    try:
        payment = Payment.objects.select_for_update().select_related("order").get(chapa_tx_ref=tx_ref)
    except Payment.DoesNotExist as exc:
        raise PaymentServiceError("Payment not found.", status_code=404) from exc

    if customer is not None:
        if customer.role != User.Role.CUSTOMER or payment.customer_id != customer.pk:
            raise PaymentServiceError("Not allowed for this payment.", status_code=403)

    if payment.status == Payment.Status.SUCCESS:
        return payment

    try:
        verify = chapa_client.verify_transaction(tx_ref)
    except ChapaClientError as exc:
        raise PaymentServiceError(_chapa_error_message(exc), status_code=502) from exc

    return _apply_verified_payment(payment, verify)


@transaction.atomic
def verify_payment_for_order(*, order_id: int, customer: User) -> Payment:
    payment = (
        Payment.objects.filter(order_id=order_id, customer=customer)
        .order_by("-created_at")
        .first()
    )
    if payment is None:
        raise PaymentServiceError("No payment found for this order.", status_code=404)
    return verify_payment_by_tx_ref(tx_ref=payment.chapa_tx_ref, customer=customer)


def verify_webhook_signature(*, body: bytes, chapa_signature: str | None, x_chapa_signature: str | None) -> bool:
    secret = getattr(settings, "CHAPA_WEBHOOK_SECRET", "") or ""
    if not secret:
        logger.error("CHAPA_WEBHOOK_SECRET is not configured; rejecting webhook.")
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    for header_value in (chapa_signature, x_chapa_signature):
        if header_value and hmac.compare_digest(expected, header_value.strip()):
            return True
    return False


@transaction.atomic
def process_chapa_webhook(*, payload: dict[str, Any]) -> Payment | None:
    tx_ref = (payload.get("tx_ref") or payload.get("trx_ref") or "").strip()
    if not tx_ref:
        logger.warning("Chapa webhook missing tx_ref: %s", payload.keys())
        return None

    try:
        payment = Payment.objects.select_for_update().select_related("order").get(chapa_tx_ref=tx_ref)
    except Payment.DoesNotExist:
        logger.warning("Chapa webhook for unknown tx_ref=%s", tx_ref)
        return None

    payment.raw_webhook_payload = payload
    payment.save(update_fields=["raw_webhook_payload", "updated_at"])

    if payment.status == Payment.Status.SUCCESS:
        return payment

    event = (payload.get("event") or "").lower()
    status = (payload.get("status") or "").lower()

    if event in {"charge.failed"} or status in {"failed", "cancelled"}:
        payment.status = Payment.Status.CANCELLED if status == "cancelled" else Payment.Status.FAILED
        payment.save(update_fields=["status", "updated_at"])
        if payment.order.payment_status == Order.PaymentStatus.PENDING:
            payment.order.payment_status = Order.PaymentStatus.FAILED
            payment.order.save(update_fields=["payment_status", "updated_at"])
        return payment

    try:
        verify = chapa_client.verify_transaction(tx_ref)
    except ChapaClientError:
        logger.exception("Webhook verify failed tx_ref=%s", tx_ref)
        return payment

    return _apply_verified_payment(payment, verify)


def get_payment_for_staff(*, payment_id: int) -> Payment:
    try:
        return Payment.objects.select_related("order", "customer", "order__restaurant").get(pk=payment_id)
    except Payment.DoesNotExist as exc:
        raise PaymentServiceError("Payment not found.", status_code=404) from exc
