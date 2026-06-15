from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default="ETB")
    chapa_tx_ref = models.CharField(max_length=128, unique=True, db_index=True)
    chapa_reference = models.CharField(max_length=128, blank=True, db_index=True)
    payment_method = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    checkout_url = models.URLField(max_length=512, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    raw_initialize_response = models.JSONField(default=dict, blank=True)
    raw_verify_response = models.JSONField(default=dict, blank=True)
    raw_webhook_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["order", "status"]),
        ]

    def __str__(self) -> str:
        return f"Payment<{self.chapa_tx_ref} {self.status}>"

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            self.Status.SUCCESS,
            self.Status.FAILED,
            self.Status.CANCELLED,
            self.Status.REFUNDED,
        }
