from __future__ import annotations

import os
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import get_valid_filename

from core.currency import DEFAULT_CURRENCY


def _safe_upload_name(filename: str) -> str:
    return get_valid_filename(os.path.basename(filename)) or "upload.jpg"


def restaurant_logo_upload_to(instance: "Restaurant", filename: str) -> str:
    rid = instance.pk if instance.pk else uuid.uuid4().hex
    return f"restaurants/{rid}/logo/{_safe_upload_name(filename)}"


def restaurant_cover_upload_to(instance: "Restaurant", filename: str) -> str:
    rid = instance.pk if instance.pk else uuid.uuid4().hex
    return f"restaurants/{rid}/cover/{_safe_upload_name(filename)}"


def menu_item_image_upload_to(instance: "MenuItem", filename: str) -> str:
    return f"menu_items/{instance.restaurant_id}/{instance.pk or 'new'}/{filename}"


class Restaurant(models.Model):
    """Partner restaurant (customer discovery + admin operations)."""

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address_text = models.CharField(max_length=500, blank=True)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    opens_at = models.TimeField(
        null=True,
        blank=True,
        help_text="Local opening time (Africa/Addis_Ababa).",
    )
    closes_at = models.TimeField(
        null=True,
        blank=True,
        help_text="Local closing time (Africa/Addis_Ababa).",
    )
    opening_hours = models.CharField(
        max_length=255,
        blank=True,
        help_text="Human-readable hours label (auto-generated from opens/closes when set).",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    logo = models.ImageField(upload_to=restaurant_logo_upload_to, blank=True, null=True)
    cover_image = models.ImageField(upload_to=restaurant_cover_upload_to, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "name")
        indexes = [
            models.Index(fields=["is_active", "-updated_at"]),
        ]

    def __str__(self) -> str:
        return self.name


class MenuCategory(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name="menu_categories",
    )
    name = models.CharField(max_length=120)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "name"],
                name="uniq_menu_category_name_per_restaurant",
            )
        ]
        indexes = [
            models.Index(fields=["restaurant", "sort_order"]),
            models.Index(fields=["restaurant", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.restaurant.name} — {self.name}"


class MenuItem(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name="menu_items",
    )
    category = models.ForeignKey(
        MenuCategory,
        on_delete=models.CASCADE,
        related_name="items",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    takeaway_box_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Per-unit takeaway box cost added to the item price.",
    )
    currency = models.CharField(max_length=8, default=DEFAULT_CURRENCY)
    is_available = models.BooleanField(default=True, db_index=True)
    image = models.ImageField(upload_to=menu_item_image_upload_to, blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "name"],
                name="uniq_menu_item_name_per_restaurant",
            )
        ]
        indexes = [
            models.Index(fields=["restaurant", "is_available"]),
            models.Index(fields=["category", "is_available"]),
        ]

    def clean(self):
        if self.category_id and self.restaurant_id:
            if self.category.restaurant_id != self.restaurant_id:
                raise ValidationError("Menu item category must belong to the same restaurant.")

    def save(self, *args, **kwargs):
        if self.category_id and not self.restaurant_id:
            self.restaurant_id = self.category.restaurant_id
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name
