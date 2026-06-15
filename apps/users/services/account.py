"""Self-service account deletion (deactivation) for mobile customers and drivers."""

from __future__ import annotations

from django.db import transaction
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.drivers.models import DriverProfile
from apps.orders.models import Order
from core.models import User

# Only in-progress deliveries block deletion (not unpaid carts or terminal states).
CUSTOMER_BLOCKING_ORDER_STATUSES = frozenset(
    {
        Order.Status.CONFIRMED,
        Order.Status.PREPARING,
        Order.Status.READY_FOR_PICKUP,
        Order.Status.ASSIGNED,
        Order.Status.PICKED_UP,
        Order.Status.DELIVERING,
    }
)

DRIVER_BLOCKING_ORDER_STATUSES = frozenset(
    {
        Order.Status.ASSIGNED,
        Order.Status.PICKED_UP,
        Order.Status.DELIVERING,
    }
)


class AccountDeletionError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _has_blocking_orders(user: User) -> bool:
    if user.role == User.Role.CUSTOMER:
        return Order.objects.filter(
            customer_id=user.pk,
            status__in=CUSTOMER_BLOCKING_ORDER_STATUSES,
        ).exists()
    if user.role == User.Role.DRIVER:
        return Order.objects.filter(
            assigned_driver_id=user.pk,
            status__in=DRIVER_BLOCKING_ORDER_STATUSES,
        ).exists()
    return False


@transaction.atomic
def delete_own_account(*, user: User, refresh_token: str | None = None) -> None:
    """
    Deactivate the authenticated customer or driver account.

    Preserves order history; blocks when open deliveries exist.
    """
    if user.role not in (User.Role.CUSTOMER, User.Role.DRIVER):
        raise AccountDeletionError(
            "This account type cannot be deleted from the app.",
            status_code=403,
        )

    if not user.is_active:
        raise AccountDeletionError("Account is already deactivated.", status_code=409)

    if _has_blocking_orders(user):
        raise AccountDeletionError(
            "Complete or cancel active orders before deleting your account.",
            status_code=409,
        )

    if refresh_token:
        try:
            RefreshToken(refresh_token).blacklist()
        except (TokenError, Exception):
            # Best-effort — account deactivation must still succeed.
            pass

    user.is_active = False
    user.save(update_fields=["is_active"])

    if user.role == User.Role.DRIVER:
        DriverProfile.objects.filter(user_id=user.pk).update(
            operational_status=DriverProfile.OperationalStatus.OFFLINE,
        )
