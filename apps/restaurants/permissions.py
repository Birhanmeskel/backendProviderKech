"""Catalog RBAC: admin writes, sales reads, customers public read (active only enforced in queryset)."""

from __future__ import annotations

from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.users.permissions import HasAnyUserRole, IsAdminUserRole
from core.models import User


def _is_catalog_admin(user) -> bool:
    """Admin role or Django superuser (e.g. createsuperuser) may manage restaurants."""
    if not getattr(user, "is_authenticated", False):
        return False
    role = (getattr(user, "role", None) or "").strip().lower()
    if role == User.Role.ADMIN:
        return True
    return bool(getattr(user, "is_superuser", False))


class IsRestaurantAdmin(BasePermission):
    """Admin-only restaurant/menu mutations."""

    message = "Admin role required to manage restaurants."

    def has_permission(self, request, view) -> bool:
        return _is_catalog_admin(request.user)


class IsRestaurantStaffRead(HasAnyUserRole):
    """Admin + sales can list all restaurants (including inactive)."""

    allowed_roles = (User.Role.ADMIN, User.Role.SALES)


class IsRestaurantCustomerOrPublic(BasePermission):
    """
    Safe reads for catalog: unauthenticated customers, customers, and staff.
    Write operations must use IsRestaurantAdmin on the view.
    """

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return False
