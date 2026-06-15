from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class CustomerProfile(models.Model):
    """
    Customer-specific profile information.

    We keep authentication in one system (User with roles) and attach
    role-specific details via profile tables.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    full_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(max_length=254, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        # Protect data consistency: customer profile should only belong to customer role.
        if self.user and getattr(self.user, "role", None) != "customer":
            raise ValidationError("CustomerProfile can only be attached to a customer user.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"CustomerProfile<{self.user}>"


class SalesProfile(models.Model):
    """Sales agent display name for admin user management and order attribution."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sales_profile",
    )
    full_name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.user and getattr(self.user, "role", None) != "sales":
            raise ValidationError("SalesProfile can only be attached to a sales user.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"SalesProfile<{self.user}>"
