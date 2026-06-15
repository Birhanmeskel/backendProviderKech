from __future__ import annotations

from django.db.models import Count, Q
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.api.serializers import (
    AssignDriverSerializer,
    DeliveryFeeQuoteInputSerializer,
    OrderCreateSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    OrderModifySerializer,
    OrderStatusUpdateSerializer,
    SalesOrderCreateSerializer,
)
from apps.orders.models import Order
from apps.drivers.models import DriverProfile
from apps.orders.services.pricing import compute_pricing, haversine_km


def _driver_context(request) -> dict:
    """Build serializer context with the requesting driver's payout percentage."""
    ctx: dict = {"request": request}
    try:
        profile = request.user.driver_profile
        ctx["driver_payout_percentage"] = profile.payout_percentage
    except (DriverProfile.DoesNotExist, AttributeError):
        pass
    return ctx
from apps.restaurants.models import Restaurant
from apps.orders.permissions import (
    CanAssignDriver,
    CanCreateCustomerOrder,
    CanCreateSalesOrder,
    CanListStaffOrders,
    CanUpdateOrderStatus,
    CanViewDriverOrders,
    IsOrderAssignedDriver,
    IsOrderCustomer,
    IsSalesOrAdmin,
)
from apps.orders.services.assignment import assign_driver_to_order
from apps.orders.services.order import (
    OrderServiceError,
    accept_order,
    create_order,
    mark_order_paid_from_payment,
    modify_order,
    transition_order_status,
)
from apps.payments.services.payment import PaymentServiceError, verify_payment_for_order
from core.models import User


class OrderPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _order_queryset():
    return (
        Order.objects.select_related(
            "customer",
            "customer__customer_profile",
            "restaurant",
            "assigned_driver",
            "assigned_driver__driver_profile",
            "sales_agent",
            "sales_agent__sales_profile",
        )
        .prefetch_related("items__menu_item")
        .annotate(item_count=Count("items", distinct=True))
    )


def _filter_orders(qs, request):
    status_param = request.query_params.get("status")
    if status_param:
        qs = qs.filter(status=status_param)
    search = (request.query_params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(reference__icontains=search)
            | Q(customer__phone__icontains=search)
            | Q(restaurant__name__icontains=search)
        )
    restaurant_id = request.query_params.get("restaurant_id")
    if restaurant_id:
        qs = qs.filter(restaurant_id=restaurant_id)
    assigned = request.query_params.get("assigned")
    if assigned == "false":
        qs = qs.filter(assigned_driver__isnull=True)
    elif assigned == "true":
        qs = qs.filter(assigned_driver__isnull=False)
    date_from = request.query_params.get("date_from")
    if date_from:
        qs = qs.filter(placed_at__date__gte=date_from)
    date_to = request.query_params.get("date_to")
    if date_to:
        qs = qs.filter(placed_at__date__lte=date_to)
    return qs.order_by("-placed_at")


class OrderListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), CanListStaffOrders()]
        user = getattr(self.request, "user", None)
        if user and user.is_authenticated and user.role == User.Role.SALES:
            return [IsAuthenticated(), CanCreateSalesOrder()]
        return [IsAuthenticated(), CanCreateCustomerOrder()]

    def get(self, request, *args, **kwargs):
        qs = _filter_orders(_order_queryset(), request)
        paginator = OrderPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = OrderListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, *args, **kwargs):
        if request.user.role == User.Role.SALES:
            body = SalesOrderCreateSerializer(data=request.data)
            body.is_valid(raise_exception=True)
            data = body.validated_data
            try:
                customer = User.objects.get(pk=data["customer_id"], role=User.Role.CUSTOMER)
            except User.DoesNotExist:
                return Response({"detail": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)
            try:
                order = create_order(
                    customer=customer,
                    restaurant_id=data["restaurant_id"],
                    items=data["items"],
                    delivery_address=data["delivery_address"],
                    customer_note=data.get("customer_note", ""),
                    sales_agent=request.user,
                    delivery_fee=data.get("delivery_fee"),
                )
            except OrderServiceError as exc:
                return Response({"detail": exc.message}, status=exc.status_code)
            requested_payment = data.get("payment_status")
            if requested_payment == Order.PaymentStatus.PAID:
                try:
                    order = mark_order_paid_from_payment(order)
                except OrderServiceError as exc:
                    return Response({"detail": exc.message}, status=exc.status_code)
            elif requested_payment == Order.PaymentStatus.FAILED:
                order.payment_status = Order.PaymentStatus.FAILED
                order.save(update_fields=["payment_status", "updated_at"])
        else:
            body = OrderCreateSerializer(data=request.data)
            body.is_valid(raise_exception=True)
            data = body.validated_data
            try:
                order = create_order(
                    customer=request.user,
                    restaurant_id=data["restaurant_id"],
                    items=data["items"],
                    delivery_address=data["delivery_address"],
                    customer_note=data.get("customer_note", ""),
                    delivery_fee=data.get("delivery_fee"),
                    payment_method=data.get("payment_method", Order.PaymentMethod.CHAPA),
                )
            except OrderServiceError as exc:
                return Response({"detail": exc.message}, status=exc.status_code)

            # POD orders skip the Chapa payment step — broadcast immediately.
            if order.payment_method == Order.PaymentMethod.POD:
                try:
                    order = transition_order_status(order, Order.Status.CONFIRMED)
                    if order.assigned_driver_id is None:
                        order = transition_order_status(order, Order.Status.SEARCHING_DRIVER)
                except OrderServiceError as exc:
                    return Response({"detail": exc.message}, status=exc.status_code)

        order = _order_queryset().get(pk=order.pk)
        return Response(
            OrderDetailSerializer(order, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class MyOrdersListView(APIView):
    permission_classes = [IsAuthenticated, CanCreateCustomerOrder]

    def get(self, request, *args, **kwargs):
        qs = _filter_orders(_order_queryset().filter(customer=request.user), request)
        paginator = OrderPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = OrderListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, order_id: int) -> Order | None:
        try:
            order = _order_queryset().get(pk=order_id)
        except Order.DoesNotExist:
            return None

        user = request.user
        if user.role in (User.Role.ADMIN, User.Role.SALES):
            return order
        if user.role == User.Role.CUSTOMER and order.customer_id == user.pk:
            return order
        if user.role == User.Role.DRIVER and order.assigned_driver_id == user.pk:
            return order
        return None

    def get(self, request, order_id: int, *args, **kwargs):
        order = self.get_object(request, order_id)
        if order is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(OrderDetailSerializer(order, context={"request": request}).data)


class ConfirmPaymentView(APIView):
    permission_classes = [IsAuthenticated, CanCreateCustomerOrder]

    def post(self, request, order_id: int, *args, **kwargs):
        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if order.customer_id != request.user.pk:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            verify_payment_for_order(order_id=order.pk, customer=request.user)
        except PaymentServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)

        order = _order_queryset().get(pk=order.pk)
        return Response(OrderDetailSerializer(order, context={"request": request}).data)


class OrderModifyView(APIView):
    permission_classes = [IsAuthenticated, CanUpdateOrderStatus]

    def patch(self, request, order_id: int, *args, **kwargs):
        try:
            order = Order.objects.select_related("restaurant").get(pk=order_id)
        except Order.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        body = OrderModifySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        items_payload = None
        if "items" in data:
            items_payload = [
                {"menu_item_id": line["menu_item_id"], "quantity": line["quantity"]}
                for line in data["items"]
            ]

        try:
            order = modify_order(
                order=order,
                items=items_payload,
                delivery_address=data.get("delivery_address"),
                customer_note=data.get("customer_note"),
            )
        except OrderServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)

        order = _order_queryset().get(pk=order.pk)
        return Response(OrderDetailSerializer(order, context={"request": request}).data)


class OrderStatusUpdateView(APIView):
    permission_classes = [IsAuthenticated, CanUpdateOrderStatus]

    def patch(self, request, order_id: int, *args, **kwargs):
        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        body = OrderStatusUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            order = transition_order_status(order, body.validated_data["status"])
        except OrderServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)

        order = _order_queryset().get(pk=order.pk)
        return Response(OrderDetailSerializer(order, context={"request": request}).data)


class AssignDriverView(APIView):
    permission_classes = [IsAuthenticated, CanAssignDriver]

    def post(self, request, order_id: int, *args, **kwargs):
        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        body = AssignDriverSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            driver = User.objects.get(pk=body.validated_data["driver_id"], role=User.Role.DRIVER)
        except User.DoesNotExist:
            return Response({"detail": "Driver not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            order = assign_driver_to_order(order=order, driver=driver, assigned_by=request.user)
        except OrderServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)

        order = _order_queryset().get(pk=order.pk)
        return Response(OrderDetailSerializer(order, context={"request": request}).data)


class DeliveryFeeQuoteView(APIView):
    """Distance-based delivery fee quote. Authenticated; sales + customers both call it."""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        body = DeliveryFeeQuoteInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            restaurant = Restaurant.objects.get(pk=data["restaurant_id"], is_active=True)
        except Restaurant.DoesNotExist:
            return Response(
                {"detail": "Restaurant not found or inactive."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if restaurant.latitude is None or restaurant.longitude is None:
            return Response(
                {"detail": "Restaurant has no coordinates set."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        distance_km = haversine_km(
            restaurant.latitude,
            restaurant.longitude,
            data["latitude"],
            data["longitude"],
        )
        pricing = compute_pricing(distance_km)
        return Response(pricing.as_dict())


class AvailableOrdersListView(APIView):
    """GET /api/v1/drivers/orders/available/ — orders waiting for a driver to accept."""

    permission_classes = [IsAuthenticated, CanViewDriverOrders]

    def get(self, request, *args, **kwargs):
        # POD orders are broadcastable even though payment_status=pending
        # (driver collects cash on delivery).
        qs = (
            _order_queryset()
            .filter(
                status=Order.Status.SEARCHING_DRIVER,
                assigned_driver__isnull=True,
            )
            .filter(
                Q(payment_status=Order.PaymentStatus.PAID)
                | Q(payment_method=Order.PaymentMethod.POD),
            )
            .order_by("placed_at")
        )
        paginator = OrderPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = OrderListSerializer(page, many=True, context=_driver_context(request))
        return paginator.get_paginated_response(serializer.data)


class AcceptOrderView(APIView):
    """POST /api/v1/drivers/orders/{id}/accept/ — atomic first-accept-wins."""

    permission_classes = [IsAuthenticated, CanViewDriverOrders]

    def post(self, request, order_id: int, *args, **kwargs):
        try:
            order = accept_order(order_id=order_id, driver=request.user)
        except OrderServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)
        order = _order_queryset().get(pk=order.pk)
        return Response(OrderDetailSerializer(order, context=_driver_context(request)).data)


class AvailableOrderDetailView(APIView):
    """GET /api/v1/drivers/orders/available/{id}/ — preview a broadcast offer before claiming."""

    permission_classes = [IsAuthenticated, CanViewDriverOrders]

    def get(self, request, order_id: int, *args, **kwargs):
        try:
            order = (
                _order_queryset()
                .filter(
                    Q(payment_status=Order.PaymentStatus.PAID)
                    | Q(payment_method=Order.PaymentMethod.POD),
                )
                .get(
                    pk=order_id,
                    status=Order.Status.SEARCHING_DRIVER,
                    assigned_driver__isnull=True,
                )
            )
        except Order.DoesNotExist:
            return Response(
                {"detail": "Order is no longer available."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(OrderDetailSerializer(order, context=_driver_context(request)).data)


class DriverOrdersListView(APIView):
    permission_classes = [IsAuthenticated, CanViewDriverOrders]

    def get(self, request, *args, **kwargs):
        qs = _filter_orders(
            _order_queryset().filter(assigned_driver=request.user),
            request,
        )
        paginator = OrderPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = OrderListSerializer(page, many=True, context=_driver_context(request))
        return paginator.get_paginated_response(serializer.data)
