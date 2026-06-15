"""
Driver approval workflow (admin operations).

Centralizes state transitions so APIs, admin, and tests share one code path.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.drivers.models import DriverProfile
from apps.users import auth_logging
from core.models import User


class DriverApprovalError(Exception):
    """Business rule violation during an approval action."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _get_driver_profile_for_user(user_id: int) -> DriverProfile:
    try:
        profile = DriverProfile.objects.select_related("user").get(user_id=user_id)
    except DriverProfile.DoesNotExist as exc:
        raise DriverApprovalError("Driver not found.", status_code=404) from exc

    if profile.user.role != User.Role.DRIVER:
        raise DriverApprovalError("User is not a driver.", status_code=404)
    return profile


@transaction.atomic
def approve_driver(*, user_id: int, admin: User) -> DriverProfile:
    profile = _get_driver_profile_for_user(user_id)

    if profile.approval_status == DriverProfile.ApprovalStatus.APPROVED:
        raise DriverApprovalError(
            "Driver is already approved.",
            status_code=409,
        )

    if profile.approval_status != DriverProfile.ApprovalStatus.PENDING:
        raise DriverApprovalError(
            f"Cannot approve driver with status '{profile.approval_status}'.",
            status_code=400,
        )

    now = timezone.now()
    profile.approval_status = DriverProfile.ApprovalStatus.APPROVED
    profile.approved_at = now
    profile.approved_by = admin
    profile.rejected_at = None
    profile.rejection_reason = ""
    profile.suspended_at = None
    profile.suspension_reason = ""
    profile.reviewed_by = admin
    profile.save(
        update_fields=[
            "approval_status",
            "approved_at",
            "approved_by",
            "rejected_at",
            "rejection_reason",
            "suspended_at",
            "suspension_reason",
            "reviewed_by",
            "updated_at",
        ]
    )

    auth_logging.log_driver_approved(admin_id=admin.id, driver_user_id=profile.user_id)
    return profile


@transaction.atomic
def reject_driver(*, user_id: int, admin: User, rejection_reason: str) -> DriverProfile:
    profile = _get_driver_profile_for_user(user_id)

    if profile.approval_status == DriverProfile.ApprovalStatus.REJECTED:
        raise DriverApprovalError(
            "Driver is already rejected.",
            status_code=409,
        )

    if profile.approval_status != DriverProfile.ApprovalStatus.PENDING:
        raise DriverApprovalError(
            f"Cannot reject driver with status '{profile.approval_status}'.",
            status_code=400,
        )

    now = timezone.now()
    profile.approval_status = DriverProfile.ApprovalStatus.REJECTED
    profile.rejected_at = now
    profile.rejection_reason = rejection_reason.strip()
    profile.reviewed_by = admin
    profile.save(
        update_fields=[
            "approval_status",
            "rejected_at",
            "rejection_reason",
            "reviewed_by",
            "updated_at",
        ]
    )

    auth_logging.log_driver_rejected(admin_id=admin.id, driver_user_id=profile.user_id)
    return profile


@transaction.atomic
def suspend_driver(*, user_id: int, admin: User, suspension_reason: str) -> DriverProfile:
    profile = _get_driver_profile_for_user(user_id)

    if profile.approval_status == DriverProfile.ApprovalStatus.SUSPENDED:
        raise DriverApprovalError(
            "Driver is already suspended.",
            status_code=409,
        )

    if profile.approval_status != DriverProfile.ApprovalStatus.APPROVED:
        raise DriverApprovalError(
            f"Cannot suspend driver with status '{profile.approval_status}'.",
            status_code=400,
        )

    now = timezone.now()
    profile.approval_status = DriverProfile.ApprovalStatus.SUSPENDED
    profile.suspended_at = now
    profile.suspension_reason = suspension_reason.strip()
    profile.reviewed_by = admin
    profile.save(
        update_fields=[
            "approval_status",
            "suspended_at",
            "suspension_reason",
            "reviewed_by",
            "updated_at",
        ]
    )

    auth_logging.log_driver_suspended(admin_id=admin.id, driver_user_id=profile.user_id)
    return profile


@transaction.atomic
def reactivate_driver(*, user_id: int, admin: User) -> DriverProfile:
    profile = _get_driver_profile_for_user(user_id)

    if profile.approval_status == DriverProfile.ApprovalStatus.APPROVED:
        raise DriverApprovalError(
            "Driver is already approved.",
            status_code=409,
        )

    if profile.approval_status != DriverProfile.ApprovalStatus.SUSPENDED:
        raise DriverApprovalError(
            f"Cannot reactivate driver with status '{profile.approval_status}'.",
            status_code=400,
        )

    now = timezone.now()
    profile.approval_status = DriverProfile.ApprovalStatus.APPROVED
    profile.approved_at = profile.approved_at or now
    profile.approved_by = profile.approved_by or admin
    profile.suspended_at = None
    profile.suspension_reason = ""
    profile.operational_status = DriverProfile.OperationalStatus.OFFLINE
    profile.reviewed_by = admin
    profile.save(
        update_fields=[
            "approval_status",
            "approved_at",
            "approved_by",
            "suspended_at",
            "suspension_reason",
            "operational_status",
            "reviewed_by",
            "updated_at",
        ]
    )

    auth_logging.log_driver_reactivated(admin_id=admin.id, driver_user_id=profile.user_id)
    return profile
