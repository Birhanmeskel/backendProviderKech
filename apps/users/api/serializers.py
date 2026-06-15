from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.drivers.models import DriverProfile
from apps.users.auth_policy import assert_jwt_eligible
from apps.users.models import CustomerProfile, SalesProfile
from apps.users.phone_utils import normalize_phone
from core.models import User

_ENUM = "Invalid credentials."


class PhoneTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    JWT login serializer for the custom phone-based user model.

    Returns access + refresh; adds role and user_id to the response body.
    """

    def validate_phone(self, value: str) -> str:
        return normalize_phone(value, obscure_invalid_format=True)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        assert_jwt_eligible(self.user)
        data["role"] = str(self.user.role)
        data["user_id"] = self.user.id
        return data


class RestrictedTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh access tokens only if the user still satisfies login policy."""

    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs["refresh"])
            user = User.objects.get(pk=refresh["user_id"])
        except (User.DoesNotExist, TokenError, KeyError) as exc:
            raise ValidationError(_ENUM) from exc

        assert_jwt_eligible(user)
        return super().validate(attrs)


class CustomerRegisterSerializer(serializers.Serializer):
    """Register a customer user + create CustomerProfile."""

    phone = serializers.CharField(max_length=32)
    password = serializers.CharField(write_only=True)
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate_phone(self, value: str) -> str:
        normalized = normalize_phone(value)
        if User.objects.filter(phone=normalized).exists():
            raise ValidationError("A user with this phone number already exists.")
        return normalized

    def validate_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise ValidationError(list(e.messages)) from e
        return value

    def create(self, validated_data):
        phone = validated_data["phone"]
        password = validated_data["password"]
        name = validated_data["name"]
        email = (validated_data.get("email") or "").strip().lower()

        with transaction.atomic():
            user = User.objects.create_user(phone=phone, password=password, role=User.Role.CUSTOMER)
            CustomerProfile.objects.create(user=user, full_name=name, email=email)
            return user


class DriverRegisterSerializer(serializers.Serializer):
    """Register a driver user + create DriverProfile with approval_status=pending."""

    phone = serializers.CharField(max_length=32)
    password = serializers.CharField(write_only=True)
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    vehicle_type = serializers.ChoiceField(
        choices=DriverProfile.VehicleType.choices,
        required=True,
    )

    def validate_phone(self, value: str) -> str:
        normalized = normalize_phone(value)
        if User.objects.filter(phone=normalized).exists():
            raise ValidationError("A user with this phone number already exists.")
        return normalized

    def validate_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise ValidationError(list(e.messages)) from e
        return value

    def create(self, validated_data):
        phone = validated_data["phone"]
        password = validated_data["password"]
        name = validated_data["name"]

        with transaction.atomic():
            user = User.objects.create_user(phone=phone, password=password, role=User.Role.DRIVER)
            DriverProfile.objects.create(
                user=user,
                full_name=name,
                email=validated_data.get("email", ""),
                vehicle_type=validated_data["vehicle_type"],
                approval_status=DriverProfile.ApprovalStatus.PENDING,
            )
            return user


class SalesAgentCreateSerializer(serializers.Serializer):
    """Create a sales-agent user account; callable only from admin-protected view."""

    phone = serializers.CharField(max_length=32)
    password = serializers.CharField(write_only=True)
    name = serializers.CharField(max_length=150)
    recovery_email = serializers.EmailField(required=False, allow_blank=True)

    def validate_phone(self, value: str) -> str:
        return normalize_phone(value)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if User.objects.filter(phone=attrs["phone"]).exists():
            raise ValidationError({"phone": ["User already exists."]})
        return attrs

    def validate_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise ValidationError(list(e.messages)) from e
        return value

    def create(self, validated_data):
        name = validated_data.pop("name").strip()
        recovery_email = (validated_data.pop("recovery_email", "") or "").strip()
        with transaction.atomic():
            user = User.objects.create_user(
                phone=validated_data["phone"],
                password=validated_data["password"],
                role=User.Role.SALES,
                recovery_email=recovery_email,
            )
            SalesProfile.objects.create(user=user, full_name=name)
            return user


class SalesAgentUpdateSerializer(serializers.Serializer):
    """Update a sales-agent's display name and/or active status (admin only)."""

    name = serializers.CharField(max_length=150, required=False, allow_blank=False)
    status = serializers.ChoiceField(choices=["active", "inactive"], required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if "name" not in attrs and "status" not in attrs:
            raise ValidationError("Provide at least one field to update.")
        return attrs

    def update(self, instance: User, validated_data):
        with transaction.atomic():
            name = validated_data.get("name")
            if name is not None:
                profile, _ = SalesProfile.objects.get_or_create(user=instance)
                profile.full_name = name.strip()
                profile.save(update_fields=["full_name"])
            status_value = validated_data.get("status")
            if status_value is not None:
                instance.is_active = status_value == "active"
                instance.save(update_fields=["is_active"])
            return instance


class PasswordResetRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    email = serializers.EmailField()
    code = serializers.CharField(min_length=4, max_length=8)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise ValidationError(list(e.messages)) from e
        return value


class CustomerMeUpdateSerializer(serializers.Serializer):
    """PATCH /auth/me — customer profile fields."""

    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    recovery_email = serializers.EmailField(required=False, allow_blank=True)


class DeleteAccountSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=False, allow_blank=True)

    def validate_refresh(self, value: str) -> str:
        return (value or "").strip()


class MeSerializer(serializers.ModelSerializer):
    """Current user + role-specific profile snippet for /auth/me."""

    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "phone",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "created_at",
            "recovery_email",
            "profile",
        )
        read_only_fields = fields

    def get_profile(self, obj: User) -> dict:
        if obj.role == User.Role.CUSTOMER:
            try:
                cp = obj.customer_profile
            except CustomerProfile.DoesNotExist:
                return {"type": "customer", "full_name": None, "email": None}
            return {
                "type": "customer",
                "full_name": cp.full_name,
                "email": cp.email or None,
            }

        if obj.role == User.Role.DRIVER:
            try:
                dp = obj.driver_profile
            except DriverProfile.DoesNotExist:
                return {"type": "driver", "full_name": None, "approval_status": None}
            return {
                "type": "driver",
                "full_name": dp.full_name,
                "approval_status": dp.approval_status,
                "vehicle_type": dp.vehicle_type or None,
            }

        return {"type": str(obj.role)}


class UserListSerializer(serializers.ModelSerializer):
    """Admin-facing user list serializer."""

    user_id = serializers.IntegerField(source="id", read_only=True)
    name = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("user_id", "phone", "name", "role", "status", "created_at")
        read_only_fields = fields

    def get_name(self, obj: User) -> str | None:
        if obj.role == User.Role.CUSTOMER:
            profile = getattr(obj, "customer_profile", None)
            if profile and profile.full_name:
                return profile.full_name
        elif obj.role == User.Role.DRIVER:
            profile = getattr(obj, "driver_profile", None)
            if profile and profile.full_name:
                return profile.full_name
        elif obj.role == User.Role.SALES:
            profile = getattr(obj, "sales_profile", None)
            if profile and profile.full_name:
                return profile.full_name
        return None

    def get_status(self, obj: User) -> str:
        if not obj.is_active:
            return "inactive"
        if obj.role == User.Role.DRIVER:
            profile = getattr(obj, "driver_profile", None)
            if profile and profile.approval_status == DriverProfile.ApprovalStatus.SUSPENDED:
                return "suspended"
        return "active"


class CustomerSearchSerializer(serializers.ModelSerializer):
    """Lightweight customer row for sales/admin order creation."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "phone", "name")
        read_only_fields = fields

    def get_name(self, obj: User) -> str:
        profile = getattr(obj, "customer_profile", None)
        if profile and profile.full_name:
            return profile.full_name
        return obj.phone
