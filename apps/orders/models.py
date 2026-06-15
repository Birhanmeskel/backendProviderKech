from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        SEARCHING_DRIVER = "searching_driver", "Searching driver"
        PREPARING = "preparing", "Preparing"
        READY_FOR_PICKUP = "ready_for_pickup", "Ready for pickup"
        ASSIGNED = "assigned", "Assigned"
        DECLINED = "declined", "Declined"
        PICKED_UP = "picked_up", "Picked up"
        DELIVERING = "delivering", "Delivering"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"

    class PaymentMethod(models.TextChoices):
        CHAPA = "chapa", "Chapa"
        POD = "pod", "Pay on delivery"

    reference = models.CharField(max_length=32, unique=True, db_index=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="customer_orders",
    )
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    sales_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_orders",
    )
    assigned_driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_orders",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    payment_status = models.CharField(
        max_length=16,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )
    payment_method = models.CharField(
        max_length=16,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CHAPA,
        db_index=True,
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    driver_payout = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    delivery_address = models.JSONField(default=dict)
    customer_note = models.TextField(blank=True)
    driver_acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the assigned driver acknowledged the manual assignment (no status change).",
    )
    placed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-placed_at",)
        indexes = [
            models.Index(fields=["customer", "-placed_at"]),
            models.Index(fields=["restaurant", "status"]),
            models.Index(fields=["assigned_driver", "status"]),
            models.Index(fields=["status", "-placed_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference} ({self.status})"

    @property
    def is_terminal(self) -> bool:
        return self.status in {self.Status.DELIVERED, self.Status.CANCELLED}


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(
        "restaurants.MenuItem",
        on_delete=models.PROTECT,
        related_name="order_lines",
    )
    item_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    takeaway_box_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ("id",)
        indexes = [models.Index(fields=["order"])]

    def __str__(self) -> str:
        return f"{self.item_name} x{self.quantity}"


class DriverDeliveryEvent(models.Model):
    """Lightweight audit trail for driver delivery actions (MVP; no dispatch)."""

    class Action(models.TextChoices):
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        DECLINED = "declined", "Declined"
        PICKED_UP = "picked_up", "Picked up"
        STARTED_DELIVERY = "started_delivery", "Started delivery"
        COMPLETED = "completed", "Completed"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="delivery_events")
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="delivery_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["order", "-created_at"])]


class DriverAssignmentLog(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="assignment_logs")
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assignment_logs",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments_made",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-assigned_at",)
        indexes = [models.Index(fields=["order", "-assigned_at"])]
