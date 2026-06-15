from __future__ import annotations

import json
import logging

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.utils.html import escape
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order
from apps.orders.permissions import CanCreateCustomerOrder, CanListStaffOrders
from apps.payments.api.serializers import (
    PaymentInitResponseSerializer,
    PaymentInitSerializer,
    PaymentSerializer,
    PaymentVerifySerializer,
)
from apps.payments.models import Payment
from apps.payments.services.payment import (
    PaymentServiceError,
    _app_return_url,
    initialize_payment,
    process_chapa_webhook,
    verify_payment_by_tx_ref,
    verify_payment_for_order,
    verify_webhook_signature,
)

logger = logging.getLogger("kech.payments.api")


class PaymentPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class PaymentInitView(APIView):
    permission_classes = [IsAuthenticated, CanCreateCustomerOrder]

    def post(self, request, *args, **kwargs):
        body = PaymentInitSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        order_id = body.validated_data["order_id"]
        try:
            order = Order.objects.get(pk=order_id, customer=request.user)
        except Order.DoesNotExist:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            payment = initialize_payment(order=order, customer=request.user)
        except PaymentServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)

        return Response(
            PaymentInitResponseSerializer(payment).data,
            status=status.HTTP_201_CREATED,
        )


class PaymentVerifyView(APIView):
    permission_classes = [IsAuthenticated, CanCreateCustomerOrder]

    def post(self, request, *args, **kwargs):
        body = PaymentVerifySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        try:
            if data.get("tx_ref"):
                payment = verify_payment_by_tx_ref(
                    tx_ref=data["tx_ref"],
                    customer=request.user,
                )
            else:
                payment = verify_payment_for_order(
                    order_id=data["order_id"],
                    customer=request.user,
                )
        except PaymentServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)

        return Response(PaymentSerializer(payment).data)


class MockChapaCheckoutView(APIView):
    """Dev/mock checkout page — simulates Chapa hosted checkout in WebView."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, *args, **kwargs):
        tx_ref = (request.query_params.get("tx_ref") or "").strip()
        if not tx_ref:
            return HttpResponse("Missing tx_ref.", status=400, content_type="text/plain")

        try:
            payment = Payment.objects.select_related("order").get(chapa_tx_ref=tx_ref)
            return_url = _app_return_url(payment.order_id, tx_ref)
        except Payment.DoesNotExist:
            return_url = _app_return_url(0, tx_ref)

        safe_return = escape(return_url)
        html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Kech mock Chapa checkout</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;text-align:center}}
button{{padding:12px 24px;font-size:16px;background:#800020;color:#fff;border:none;border-radius:8px}}</style>
</head>
<body>
<h1>Mock Chapa checkout</h1>
<p>Transaction: <code>{escape(tx_ref)}</code></p>
<p><a href="{safe_return}"><button type="button">Complete test payment</button></a></p>
</body></html>"""
        return HttpResponse(html, content_type="text/html; charset=utf-8")


class ChapaReturnRedirectView(APIView):
    """
    Browser return URL after Chapa checkout (http/https).
    Redirects to the mobile deep link configured in CHAPA_APP_RETURN_URL.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, *args, **kwargs):
        tx_ref = (request.query_params.get("tx_ref") or request.query_params.get("trx_ref") or "").strip()
        order_id_raw = request.query_params.get("order_id")
        order_id = int(order_id_raw) if order_id_raw and str(order_id_raw).isdigit() else 0
        if not tx_ref:
            return HttpResponse("Missing tx_ref.", status=400, content_type="text/plain")

        deep_link = _app_return_url(order_id, tx_ref)
        safe_target = escape(deep_link)
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <meta http-equiv="refresh" content="0;url={safe_target}"/>
  <title>Returning to Kech</title>
</head>
<body>
  <p>Payment complete. <a href="{safe_target}">Return to the app</a>.</p>
  <script>window.location.replace("{safe_target}");</script>
</body>
</html>"""
        return HttpResponse(html, content_type="text/html; charset=utf-8")


class ChapaCallbackView(APIView):
    """Chapa redirect/callback — verify transaction server-side (do not trust query params alone)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, *args, **kwargs):
        tx_ref = (request.query_params.get("tx_ref") or request.query_params.get("trx_ref") or "").strip()
        if not tx_ref:
            return Response({"detail": "tx_ref required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payment = verify_payment_by_tx_ref(tx_ref=tx_ref, customer=None)
        except PaymentServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)
        return Response(
            {
                "detail": "ok",
                "payment_status": payment.status,
                "order_id": payment.order_id,
            }
        )


class ChapaWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request, *args, **kwargs):
        raw_body = request.body
        chapa_sig = request.headers.get("Chapa-Signature") or request.headers.get("chapa-signature")
        x_sig = request.headers.get("x-chapa-signature")

        if not verify_webhook_signature(
            body=raw_body,
            chapa_signature=chapa_sig,
            x_chapa_signature=x_sig,
        ):
            logger.warning("Rejected Chapa webhook: invalid signature")
            return Response({"detail": "Invalid signature."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response({"detail": "Invalid JSON."}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(payload, dict):
            return Response({"detail": "Invalid payload."}, status=status.HTTP_400_BAD_REQUEST)

        process_chapa_webhook(payload=payload)
        return Response({"detail": "ok"})


class PaymentListView(APIView):
    permission_classes = [IsAuthenticated, CanListStaffOrders]

    def get(self, request, *args, **kwargs):
        qs = Payment.objects.select_related("order", "customer", "order__restaurant").order_by("-created_at")

        status_param = (request.query_params.get("status") or "").strip()
        if status_param:
            qs = qs.filter(status=status_param)

        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(chapa_tx_ref__icontains=search)
                | Q(chapa_reference__icontains=search)
                | Q(order__reference__icontains=search)
                | Q(customer__phone__icontains=search)
            )

        order_id = request.query_params.get("order_id")
        if order_id not in (None, ""):
            try:
                qs = qs.filter(order_id=int(order_id))
            except (TypeError, ValueError):
                return Response({"detail": "Invalid order_id."}, status=status.HTTP_400_BAD_REQUEST)

        paginator = PaymentPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            serializer = PaymentSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = PaymentSerializer(qs, many=True)
        return Response(serializer.data)


class PaymentDetailView(APIView):
    permission_classes = [IsAuthenticated, CanListStaffOrders]

    def get(self, request, payment_id: int, *args, **kwargs):
        try:
            payment = Payment.objects.select_related("order", "customer", "order__restaurant").get(
                pk=payment_id
            )
        except Payment.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(PaymentSerializer(payment).data)
