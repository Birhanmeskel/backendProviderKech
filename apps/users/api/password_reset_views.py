from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.api.serializers import PasswordResetConfirmSerializer, PasswordResetRequestSerializer
from apps.users.services.password_reset import PasswordResetError, confirm_password_reset, request_password_reset


class PasswordResetRequestView(APIView):
    """POST /api/v1/auth/password-reset/request/"""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        body = PasswordResetRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            payload = request_password_reset(
                phone=body.validated_data["phone"],
                email=body.validated_data["email"],
            )
        except PasswordResetError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)
        return Response(payload, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """POST /api/v1/auth/password-reset/confirm/"""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        body = PasswordResetConfirmSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            confirm_password_reset(
                phone=body.validated_data["phone"],
                email=body.validated_data["email"],
                code=body.validated_data["code"],
                new_password=body.validated_data["new_password"],
            )
        except PasswordResetError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)
        return Response(
            {"message": "Password updated. You can sign in with your new password."},
            status=status.HTTP_200_OK,
        )
