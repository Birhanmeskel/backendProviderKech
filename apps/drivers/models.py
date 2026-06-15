from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class DriverProfile(models.Model):
    """
    Driver-specific operational profile.

    Authentication remains in a single User model. This table stores
    role-specific fields for users with role=driver.
    """

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    class OperationalStatus(models.TextChoices):
        OFFLINE = "offline", "Offline"
        ONLINE = "online", "Online"
        BUSY = "busy", "Busy"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="driver_profile",
    )
    class VehicleType(models.TextChoices):
        SEDAN = "sedan", "Sedan"
        MOTORBIKE = "motorbike", "Motorbike"

    full_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    vehicle_type = models.CharField(
        max_length=20,
        choices=VehicleType.choices,
        blank=True,
    )
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    documents_submitted_at = models.DateTimeField(null=True, blank=True)
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        db_index=True,
    )
    operational_status = models.CharField(
        max_length=16,
        choices=OperationalStatus.choices,
        default=OperationalStatus.OFFLINE,
        db_index=True,
    )

    payout_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("60.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Percentage of delivery fee the driver receives (0–100).",
    )
    balance_adjustment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=(
            "Manual adjustment applied on top of computed balance "
            "(sum of driver_payout from delivered orders). "
            "Typically reduced (negative) when admin pays the driver."
        ),
    )
    debt_adjustment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=(
            "Manual adjustment applied on top of computed debt "
            "(sum of platform_fee from delivered POD orders). "
            "Typically reduced (negative) when driver settles cash with the platform."
        ),
    )

    # Approval workflow audit fields (set by admin APIs, not self-service).
    approved_at = models.DateTimeField(null=True, blank=True, db_index=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drivers_approved",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drivers_reviewed",
    )
    rejection_reason = models.TextField(blank=True)
    suspension_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        # Protect data consistency: driver profile should only belong to driver role.
        if self.user and getattr(self.user, "role", None) != "driver":
            raise ValidationError("DriverProfile can only be attached to a driver user.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def reviewed_at(self):
        """Most recent review timestamp for mobile status UX."""
        if self.approval_status == self.ApprovalStatus.APPROVED:
            return self.approved_at
        if self.approval_status == self.ApprovalStatus.REJECTED:
            return self.rejected_at
        if self.approval_status == self.ApprovalStatus.SUSPENDED:
            return self.suspended_at
        return None

    def __str__(self) -> str:
        return f"DriverProfile<{self.user}> [{self.approval_status}]"


def driver_document_upload_to(instance: "DriverDocument", filename: str) -> str:
    return f"driver_documents/{instance.user_id}/{instance.document_type}/{filename}"


class DriverDocument(models.Model):
    """Uploaded verification documents for driver onboarding."""

    class DocumentType(models.TextChoices):
        LICENSE = "license", "Driver license"
        NATIONAL_ID = "national_id", "National ID"
        VEHICLE_REGISTRATION = "vehicle_registration", "Vehicle registration"
        PROFILE_PHOTO = "profile_photo", "Profile photo"

    REQUIRED_TYPES = frozenset(
        {
            DocumentType.LICENSE,
            DocumentType.NATIONAL_ID,
            DocumentType.VEHICLE_REGISTRATION,
        }
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="driver_documents",
    )
    document_type = models.CharField(max_length=32, choices=DocumentType.choices)
    file = models.FileField(upload_to=driver_document_upload_to)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "document_type"],
                name="uniq_driver_document_per_type",
            )
        ]

    def __str__(self) -> str:
        return f"DriverDocument<{self.user_id}:{self.document_type}>"
