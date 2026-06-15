"""Order RBAC — enforce on every endpoint; never trust frontend role checks."""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.orders.models import Order
from apps.users.permissions import HasAnyUserRole, IsApprovedDriver
from core.models import User


class IsSalesOrAdmin(HasAnyUserRole):
    allowed_roles = (User.Role.ADMIN, User.Role.SALES)


class IsOrderCustomer(BasePermission):
    """Object-level: customer owns the order."""

    def has_object_permission(self, request, view, obj: Order) -> bool:
        user = request.user
        return bool(user.is_authenticated and obj.customer_id == user.pk)


class IsOrderAssignedDriver(BasePermission):
    """Object-level: approved driver assigned to this order."""

    def has_object_permission(self, request, view, obj: Order) -> bool:
        user = request.user
        if not user.is_authenticated or user.role != User.Role.DRIVER:
            return False
        return obj.assigned_driver_id == user.pk


class CanListStaffOrders(IsSalesOrAdmin):
    pass


class CanCreateCustomerOrder(HasAnyUserRole):
    allowed_roles = (User.Role.CUSTOMER,)


class CanCreateSalesOrder(IsSalesOrAdmin):
    pass


class CanAssignDriver(IsSalesOrAdmin):
    pass


class CanUpdateOrderStatus(IsSalesOrAdmin):
    pass


class CanViewDriverOrders(IsApprovedDriver):
    pass
