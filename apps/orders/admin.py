from django.contrib import admin

from apps.orders.models import DriverAssignmentLog, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("item_name", "quantity", "unit_price", "total_price")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "customer", "restaurant", "status", "total_amount", "placed_at")
    list_filter = ("status", "payment_status")
    search_fields = ("reference", "customer__phone", "restaurant__name")
    inlines = [OrderItemInline]


@admin.register(DriverAssignmentLog)
class DriverAssignmentLogAdmin(admin.ModelAdmin):
    list_display = ("order", "driver", "assigned_by", "assigned_at")
