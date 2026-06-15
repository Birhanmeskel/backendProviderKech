"""Driver-owned delivery actions (MVP manual assign → execute)."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.drivers.models import DriverProfile
from apps.drivers.services.availability import (
    AvailabilityError,
    assert_driver_online_for_delivery,
    refresh_operational_status,
)
from apps.orders.models import DriverDeliveryEvent, Order
from apps.orders.services.order import OrderServiceError, transition_order_status
from core.models import User


def _driver_profile(driver: User) -> DriverProfile:
    try:
        return driver.driver_profile
    except DriverProfile.DoesNotExist as exc:
        raise OrderServiceError("Driver profile not found.", status_code=404) from exc


def _log_event(*, order: Order, driver: User, action: str) -> None:
    DriverDeliveryEvent.objects.create(order=order, driver=driver, action=action)


@transaction.atomic
def _locked_order(order_id: int) -> Order:
    return Order.objects.select_for_update().get(pk=order_id)


def _assert_driver_owns_order(order: Order, driver: User) -> None:
    if order.assigned_driver_id != driver.pk:
        raise OrderServiceError("You are not assigned to this order.", status_code=403)


def _assert_operational(driver: User) -> DriverProfile:
    profile = _driver_profile(driver)
    if profile.approval_status != DriverProfile.ApprovalStatus.APPROVED:
        raise OrderServiceError("Driver is not approved.", status_code=403)
    if not driver.is_active:
        raise OrderServiceError("Driver account is inactive.", status_code=403)
    try:
        assert_driver_online_for_delivery(profile)
    except AvailabilityError as exc:
        raise OrderServiceError(exc.message, status_code=exc.status_code) from exc
    return profile


@transaction.atomic
def acknowledge_assignment(*, order_id: int, driver: User) -> Order:
    """
    Assignment acknowledgment only — status stays ``assigned``.
    Idempotent if already acknowledged.
    """
    profile = _assert_operational(driver)
    order = _locked_order(order_id)
    _assert_driver_owns_order(order, driver)

    if order.is_terminal:
        raise OrderServiceError("Order is no longer active.", status_code=409)

    if order.status != Order.Status.ASSIGNED:
        raise OrderServiceError(
            "Order must be in assigned status to acknowledge.",
            status_code=409,
        )

    if order.driver_acknowledged_at is None:
        order.driver_acknowledged_at = timezone.now()
        order.updated_at = timezone.now()
        order.save(update_fields=["driver_acknowledged_at", "updated_at"])
        _log_event(order=order, driver=driver, action=DriverDeliveryEvent.Action.ACKNOWLEDGED)

    refresh_operational_status(profile)
    return order


@transaction.atomic
def decline_assignment(*, order_id: int, driver: User) -> Order:
    """
    Driver refuses an assigned delivery before pickup.
    Order moves to ``declined`` so dispatch/admin can reassign.
    """
    profile = _driver_profile(driver)
    if profile.approval_status != DriverProfile.ApprovalStatus.APPROVED:
        raise OrderServiceError("Driver is not approved.", status_code=403)
    if not driver.is_active:
        raise OrderServiceError("Driver account is inactive.", status_code=403)

    order = _locked_order(order_id)
    _assert_driver_owns_order(order, driver)

    if order.is_terminal:
        raise OrderServiceError("Order is no longer active.", status_code=409)

    if order.status != Order.Status.ASSIGNED:
        raise OrderServiceError(
            "Only assigned orders can be declined.",
            status_code=409,
        )

    order = transition_order_status(order, Order.Status.DECLINED)
    order.driver_acknowledged_at = None
    order.updated_at = timezone.now()
    order.save(update_fields=["driver_acknowledged_at", "updated_at"])
    _log_event(order=order, driver=driver, action=DriverDeliveryEvent.Action.DECLINED)
    refresh_operational_status(profile)
    return order


@transaction.atomic
def mark_picked_up(*, order_id: int, driver: User) -> Order:
    profile = _assert_operational(driver)
    order = _locked_order(order_id)
    _assert_driver_owns_order(order, driver)
    order = transition_order_status(order, Order.Status.PICKED_UP)
    _log_event(order=order, driver=driver, action=DriverDeliveryEvent.Action.PICKED_UP)
    refresh_operational_status(profile)
    return order


@transaction.atomic
def start_delivery(*, order_id: int, driver: User) -> Order:
    profile = _assert_operational(driver)
    order = _locked_order(order_id)
    _assert_driver_owns_order(order, driver)
    order = transition_order_status(order, Order.Status.DELIVERING)
    _log_event(order=order, driver=driver, action=DriverDeliveryEvent.Action.STARTED_DELIVERY)
    refresh_operational_status(profile)
    return order


@transaction.atomic
def complete_delivery(*, order_id: int, driver: User) -> Order:
    profile = _assert_operational(driver)
    order = _locked_order(order_id)
    _assert_driver_owns_order(order, driver)
    order = transition_order_status(order, Order.Status.DELIVERED)
    if (
        order.payment_method == Order.PaymentMethod.POD
        and order.payment_status != Order.PaymentStatus.PAID
    ):
        order.payment_status = Order.PaymentStatus.PAID
        order.save(update_fields=["payment_status", "updated_at"])
    _log_event(order=order, driver=driver, action=DriverDeliveryEvent.Action.COMPLETED)
    refresh_operational_status(profile)
    return order
