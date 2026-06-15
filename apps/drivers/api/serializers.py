from __future__ import annotations

from rest_framework import serializers

from apps.drivers.models import DriverProfile


class SuspendedDriverSerializer(serializers.ModelSerializer):
    """Admin list of suspended drivers."""

    user_id = serializers.IntegerField(source="user.id", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)

    class Meta:
        model = DriverProfile
        fields = (
            "user_id",
            "full_name",
            "email",
            "phone",
            "vehicle_type",
            "suspended_at",
            "suspension_reason",
        )
        read_only_fields = fields


class PendingDriverSerializer(serializers.ModelSerializer):
    """Admin list of drivers awaiting review."""

    user_id = serializers.IntegerField(source="user.id", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    documents_submitted = serializers.SerializerMethodField()
    uploaded_document_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = DriverProfile
        fields = (
            "user_id",
            "full_name",
            "email",
            "phone",
            "approval_status",
            "created_at",
            "documents_submitted",
            "uploaded_document_count",
        )
        read_only_fields = fields

    def get_documents_submitted(self, obj: DriverProfile) -> bool:
        return obj.documents_submitted_at is not None


class AdminDriverDocumentSerializer(serializers.Serializer):
    document_type = serializers.CharField()
    document_type_label = serializers.CharField()
    file_url = serializers.URLField(allow_null=True)
    uploaded_at = serializers.DateTimeField()
    is_pdf = serializers.BooleanField()


class DriverActionResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    driver_id = serializers.IntegerField()
    approval_status = serializers.CharField()


class RejectDriverSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(max_length=1000, trim_whitespace=True)

    def validate_rejection_reason(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Rejection reason is required.")
        return value.strip()


class SuspendDriverSerializer(serializers.Serializer):
    suspension_reason = serializers.CharField(max_length=1000, trim_whitespace=True)

    def validate_suspension_reason(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Suspension reason is required.")
        return value.strip()


class PayoutPercentageSerializer(serializers.Serializer):
    payout_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100,
    )


class DriverProfileUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    vehicle_type = serializers.ChoiceField(
        choices=DriverProfile.VehicleType.choices,
        required=False,
        allow_blank=True,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class DriverAvailabilityUpdateSerializer(serializers.Serializer):
    operational_status = serializers.ChoiceField(
        choices=[
            DriverProfile.OperationalStatus.OFFLINE,
            DriverProfile.OperationalStatus.ONLINE,
        ],
    )


class DriverStatusSerializer(serializers.ModelSerializer):
    """
    Onboarding status for the authenticated driver (mobile UX).

    Pending drivers typically learn status from registration; this endpoint supports
    approved drivers and re-checks after admin actions when a valid session exists.
    """

    reviewed_at = serializers.DateTimeField(read_only=True)
    phone_verified = serializers.SerializerMethodField()
    documents_submitted = serializers.SerializerMethodField()
    rejection_reason = serializers.SerializerMethodField()
    suspension_reason = serializers.SerializerMethodField()

    def get_phone_verified(self, obj: DriverProfile) -> bool:
        return obj.phone_verified_at is not None

    def get_documents_submitted(self, obj: DriverProfile) -> bool:
        return obj.documents_submitted_at is not None

    operational_status = serializers.CharField(read_only=True)

    class Meta:
        model = DriverProfile
        fields = (
            "approval_status",
            "operational_status",
            "reviewed_at",
            "rejection_reason",
            "suspension_reason",
            "phone_verified",
            "documents_submitted",
        )
        read_only_fields = fields

    def get_rejection_reason(self, obj: DriverProfile) -> str | None:
        if obj.approval_status == DriverProfile.ApprovalStatus.REJECTED:
            return obj.rejection_reason or None
        return None

    def get_suspension_reason(self, obj: DriverProfile) -> str | None:
        if obj.approval_status == DriverProfile.ApprovalStatus.SUSPENDED:
            return obj.suspension_reason or None
        return None
