"""Driver assignment rules and audit logging."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.drivers.models import DriverProfile
from apps.orders.models import DriverAssignmentLog, Order
from apps.orders.services.order import MAX_ACTIVE_DRIVER_ORDERS, OrderServiceError
from apps.orders.services.pricing import apply_driver_percentage
from core.models import User

ACTIVE_DRIVER_STATUSES = {
    Order.Status.ASSIGNED,
    Order.Status.PICKED_UP,
    Order.Status.DELIVERING,
}


@transaction.atomic
def assign_driver_to_order(*, order: Order, driver: User, assigned_by: User) -> Order:
    if order.is_terminal:
        raise OrderServiceError("Cannot assign driver to a completed order.", status_code=409)

    if order.status == Order.Status.CANCELLED:
        raise OrderServiceError("Cancelled orders cannot be reassigned.", status_code=409)

    if driver.role != User.Role.DRIVER:
        raise OrderServiceError("Selected user is not a driver.", status_code=400)

    try:
        profile = driver.driver_profile
    except DriverProfile.DoesNotExist as exc:
        raise OrderServiceError("Driver profile not found.", status_code=404) from exc

    if profile.approval_status != DriverProfile.ApprovalStatus.APPROVED:
        raise OrderServiceError("Only approved drivers can be assigned.", status_code=400)

    if not driver.is_active:
        raise OrderServiceError("Driver account is inactive.", status_code=400)

    if profile.operational_status == DriverProfile.OperationalStatus.OFFLINE:
        raise OrderServiceError(
            "Only online drivers can receive new assignments.",
            status_code=409,
        )

    active_count = Order.objects.filter(
        assigned_driver=driver,
        status__in=ACTIVE_DRIVER_STATUSES,
    ).exclude(pk=order.pk).count()

    if active_count >= MAX_ACTIVE_DRIVER_ORDERS:
        raise OrderServiceError(
            f"Driver already has {MAX_ACTIVE_DRIVER_ORDERS} active deliveries.",
            status_code=409,
        )

    # Don't hand a declined order back to the driver who refused it —
    # main's policy. Other drivers are fair game.
    if (
        order.status == Order.Status.DECLINED
        and order.assigned_driver_id == driver.id
    ):
        raise OrderServiceError(
            "This driver previously declined this delivery.",
            status_code=409,
        )

    order.assigned_driver = driver

    driver_payout, platform_fee = apply_driver_percentage(
        order.delivery_fee, profile.payout_percentage,
    )
    order.driver_payout = driver_payout
    order.platform_fee = platform_fee

    if order.status in {
        Order.Status.PENDING,
        Order.Status.CONFIRMED,
        Order.Status.SEARCHING_DRIVER,
        Order.Status.PREPARING,
        Order.Status.READY_FOR_PICKUP,
        Order.Status.DECLINED,
    }:
        order.status = Order.Status.ASSIGNED
    order.driver_acknowledged_at = None
    order.updated_at = timezone.now()
    order.save(
        update_fields=[
            "assigned_driver", "status", "driver_acknowledged_at",
            "driver_payout", "platform_fee", "updated_at",
        ],
    )

    DriverAssignmentLog.objects.create(
        order=order,
        driver=driver,
        assigned_by=assigned_by,
    )

    from apps.drivers.services.availability import refresh_operational_status

    refresh_operational_status(profile)
    return order
