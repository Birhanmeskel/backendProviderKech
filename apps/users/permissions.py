"""
Role-based permissions for DRF (enforce at API layer for every business endpoint).
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.drivers.models import DriverProfile
from core.models import User


class HasAnyUserRole(BasePermission):
    """
    Allow only users whose role is in ``allowed_roles`` (subset of User.Role values).
    """

    allowed_roles: tuple[str, ...] = ()

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user.is_authenticated:
            return False
        return user.role in self.allowed_roles


class IsCustomer(HasAnyUserRole):
    allowed_roles = (User.Role.CUSTOMER,)


class IsDriver(HasAnyUserRole):
    allowed_roles = (User.Role.DRIVER,)


class IsApprovedDriver(BasePermission):
    """
    Driver endpoints that require an operational (fleet-ready) account.

    Login-time checks (``assert_jwt_eligible``) are necessary but not sufficient:
    a suspended driver could otherwise keep using a valid access token until expiry.
    Combine this permission with ``SafeJWTAuthentication`` on every driver business view.
    """

    message = "Driver account is not approved for this action."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user.is_authenticated or not user.is_active:
            return False
        if user.role != User.Role.DRIVER:
            return False

        try:
            profile = user.driver_profile
        except DriverProfile.DoesNotExist:
            return False

        return profile.approval_status == DriverProfile.ApprovalStatus.APPROVED


class IsPlatformStaff(HasAnyUserRole):
    """Admin or Sales — operational dashboards (MVP scope)."""

    allowed_roles = (User.Role.ADMIN, User.Role.SALES)


class IsAdminOrSales(IsPlatformStaff):
    """Alias matching common naming; same as IsPlatformStaff."""

    pass


class IsAdministrator(HasAnyUserRole):
    allowed_roles = (User.Role.ADMIN,)


class IsAdminUserRole(HasAnyUserRole):
    """Explicit permission class for endpoints that require admin role only."""

    allowed_roles = (User.Role.ADMIN,)
