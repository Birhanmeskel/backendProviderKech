from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.drivers.models import DriverProfile
from apps.drivers.permissions import HasDriverOnboardingToken
from apps.users.otp_service import OtpError, send_code, verify_code
from apps.users.phone_utils import normalize_phone
from core.models import User

DRIVER_REGISTER_PURPOSE = "driver_register"


class OtpSendSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)

    def validate_phone(self, value: str) -> str:
        return normalize_phone(value)


class OtpVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    code = serializers.CharField(min_length=6, max_length=6)

    def validate_phone(self, value: str) -> str:
        return normalize_phone(value)


class DriverOnboardingOtpSendView(APIView):
    """POST /api/v1/auth/otp/driver/send/ — requires X-Registration-Token."""

    permission_classes = [HasDriverOnboardingToken]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_otp_send"

    def post(self, request, *args, **kwargs):
        body = OtpSendSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        phone = body.validated_data["phone"]

        user = get_object_or_404(User, pk=request.onboarding_user_id, role=User.Role.DRIVER)
        if user.phone != phone:
            return Response(
                {"detail": "Phone does not match registration."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        send_code(purpose=DRIVER_REGISTER_PURPOSE, phone=phone)
        return Response({"message": "Verification code sent."}, status=status.HTTP_200_OK)


class DriverOnboardingOtpVerifyView(APIView):
    """POST /api/v1/auth/otp/driver/verify/ — marks phone verified on success."""

    permission_classes = [HasDriverOnboardingToken]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_otp_verify"

    def post(self, request, *args, **kwargs):
        body = OtpVerifySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        phone = body.validated_data["phone"]
        code = body.validated_data["code"]

        user = get_object_or_404(User, pk=request.onboarding_user_id, role=User.Role.DRIVER)
        if user.phone != phone:
            return Response(
                {"detail": "Phone does not match registration."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            verify_code(purpose=DRIVER_REGISTER_PURPOSE, phone=phone, code=code)
        except OtpError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)

        profile = get_object_or_404(DriverProfile, user=user)
        if not profile.phone_verified_at:
            profile.phone_verified_at = timezone.now()
            profile.save(update_fields=["phone_verified_at", "updated_at"])

        return Response(
            {
                "message": "Phone verified successfully.",
                "phone_verified": True,
                "approval_status": profile.approval_status,
            },
            status=status.HTTP_200_OK,
        )
