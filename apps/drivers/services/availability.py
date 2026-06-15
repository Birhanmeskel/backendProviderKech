"""MVP driver operational availability (offline / online / busy)."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.drivers.models import DriverProfile
from apps.orders.services.assignment import ACTIVE_DRIVER_STATUSES
from apps.orders.models import Order
from core.models import User


class AvailabilityError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def active_delivery_count(driver: User) -> int:
    return Order.objects.filter(
        assigned_driver=driver,
        status__in=ACTIVE_DRIVER_STATUSES,
    ).count()


@transaction.atomic
def refresh_operational_status(profile: DriverProfile) -> DriverProfile:
    """
  If the driver has active deliveries, mark busy (unless explicitly offline).
  If no active deliveries and was busy, return to online.
    """
    profile = DriverProfile.objects.select_for_update().get(pk=profile.pk)
    if profile.operational_status == DriverProfile.OperationalStatus.OFFLINE:
        return profile

    if active_delivery_count(profile.user) > 0:
        if profile.operational_status != DriverProfile.OperationalStatus.BUSY:
            profile.operational_status = DriverProfile.OperationalStatus.BUSY
            profile.updated_at = timezone.now()
            profile.save(update_fields=["operational_status", "updated_at"])
        return profile

    if profile.operational_status == DriverProfile.OperationalStatus.BUSY:
        profile.operational_status = DriverProfile.OperationalStatus.ONLINE
        profile.updated_at = timezone.now()
        profile.save(update_fields=["operational_status", "updated_at"])
    return profile


def get_availability(profile: DriverProfile) -> dict:
    refresh_operational_status(profile)
    profile.refresh_from_db()
    return {
        "operational_status": profile.operational_status,
        "active_delivery_count": active_delivery_count(profile.user),
    }


@transaction.atomic
def set_operational_status(profile: DriverProfile, status: str) -> DriverProfile:
    """Drivers may toggle offline/online only; busy is derived from active orders."""
    if status not in {
        DriverProfile.OperationalStatus.OFFLINE,
        DriverProfile.OperationalStatus.ONLINE,
    }:
        raise AvailabilityError(
            "Invalid status. Use offline or online.",
            status_code=400,
        )

    if profile.approval_status != DriverProfile.ApprovalStatus.APPROVED:
        raise AvailabilityError("Only approved drivers can change availability.", status_code=403)

    if not profile.user.is_active:
        raise AvailabilityError("Driver account is inactive.", status_code=403)

    profile = DriverProfile.objects.select_for_update().get(pk=profile.pk)

    if status == DriverProfile.OperationalStatus.OFFLINE:
        if active_delivery_count(profile.user) > 0:
            raise AvailabilityError(
                "Cannot go offline while you have active deliveries.",
                status_code=409,
            )
        profile.operational_status = DriverProfile.OperationalStatus.OFFLINE
        profile.updated_at = timezone.now()
        profile.save(update_fields=["operational_status", "updated_at"])
        return profile

    # Going online
    profile.operational_status = DriverProfile.OperationalStatus.ONLINE
    profile.updated_at = timezone.now()
    profile.save(update_fields=["operational_status", "updated_at"])
    return refresh_operational_status(profile)


def assert_driver_online_for_delivery(profile: DriverProfile) -> None:
    """Offline drivers cannot execute delivery actions (MVP REST toggle only)."""
    refresh_operational_status(profile)
    profile.refresh_from_db()
    if profile.operational_status == DriverProfile.OperationalStatus.OFFLINE:
        raise AvailabilityError("Go online to perform delivery actions.", status_code=409)
