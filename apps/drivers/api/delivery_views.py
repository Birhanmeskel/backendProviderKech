"""Driver delivery execution endpoints (MVP manual assignment workflow)."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.drivers.models import DriverProfile
from apps.drivers.services.availability import AvailabilityError, get_availability, set_operational_status
from apps.orders.api.serializers import OrderDetailSerializer
from apps.orders.api.views import _driver_context, _order_queryset
from apps.orders.models import Order
from apps.orders.permissions import CanViewDriverOrders
from apps.orders.services.driver_delivery import (
    acknowledge_assignment,
    complete_delivery,
    decline_assignment,
    mark_picked_up,
    start_delivery,
)
from apps.orders.services.order import OrderServiceError
from apps.users.permissions import IsApprovedDriver

from .serializers import DriverAvailabilityUpdateSerializer


def _detail_response(request, order: Order) -> Response:
    order = _order_queryset().get(pk=order.pk)
    return Response(OrderDetailSerializer(order, context=_driver_context(request)).data)


class DriverAvailabilityView(APIView):
    """GET/PATCH /api/v1/drivers/me/availability/ — offline/online toggle (busy is derived)."""

    permission_classes = [IsAuthenticated, IsApprovedDriver]

    def get(self, request, *args, **kwargs):
        profile = request.user.driver_profile
        return Response(get_availability(profile))

    def patch(self, request, *args, **kwargs):
        body = DriverAvailabilityUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        profile = request.user.driver_profile
        try:
            set_operational_status(profile, body.validated_data["operational_status"])
        except AvailabilityError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)
        return Response(get_availability(profile))


class DriverOrderDetailView(APIView):
    """GET /api/v1/drivers/orders/<id>/ — assigned driver only."""

    permission_classes = [IsAuthenticated, CanViewDriverOrders]

    def get_object(self, request, order_id: int) -> Order | None:
        try:
            return _order_queryset().get(pk=order_id, assigned_driver=request.user)
        except Order.DoesNotExist:
            return None

    def get(self, request, order_id: int, *args, **kwargs):
        order = self.get_object(request, order_id)
        if order is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return _detail_response(request, order)


class _DriverOrderActionView(APIView):
    permission_classes = [IsAuthenticated, CanViewDriverOrders]

    action_handler = None

    def post(self, request, order_id: int, *args, **kwargs):
        try:
            order = _order_queryset().get(pk=order_id, assigned_driver=request.user)
        except Order.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        handler = self.__class__.action_handler
        try:
            order = handler(order_id=order_id, driver=request.user)
        except OrderServiceError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)

        return _detail_response(request, order)


class DriverOrderAcceptView(_DriverOrderActionView):
    """POST accept — acknowledgment only; status remains assigned."""

    action_handler = acknowledge_assignment


class DriverOrderDeclineView(_DriverOrderActionView):
    """POST decline — order status becomes declined for dispatch."""

    action_handler = decline_assignment


class DriverOrderPickupView(_DriverOrderActionView):
    action_handler = mark_picked_up


class DriverOrderStartDeliveryView(_DriverOrderActionView):
    action_handler = start_delivery


class DriverOrderCompleteView(_DriverOrderActionView):
    action_handler = complete_delivery
