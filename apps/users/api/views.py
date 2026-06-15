from django.db.models import Q

from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from apps.users import auth_logging
from apps.users.onboarding_token import issue as issue_onboarding_token
from apps.users.permissions import IsAdminOrSales, IsAdminUserRole
from core.models import User

from apps.users.services.account import AccountDeletionError, delete_own_account

from .serializers import (
    CustomerRegisterSerializer,
    CustomerSearchSerializer,
    DeleteAccountSerializer,
    DriverRegisterSerializer,
    CustomerMeUpdateSerializer,
    MeSerializer,
    PhoneTokenObtainPairSerializer,
    RestrictedTokenRefreshSerializer,
    SalesAgentCreateSerializer,
    SalesAgentUpdateSerializer,
    UserListSerializer,
)


class PhoneTokenObtainPairView(TokenObtainPairView):
    """
    Single login entrypoint: POST returns access + refresh + user_id + role.

    Use this instead of a separate access-only login route.
    """

    serializer_class = PhoneTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_token"

    def post(self, request, *args, **kwargs):
        phone = request.data.get("phone") if isinstance(request.data, dict) else None
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            auth_logging.log_token_success(phone)
        return response


class RestrictedTokenRefreshView(TokenRefreshView):
    serializer_class = RestrictedTokenRefreshSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_refresh"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED):
            auth_logging.log_token_failure(None, response.status_code)
            response.data = {"detail": "Invalid credentials."}
        return response


class ThrottledTokenVerifyView(TokenVerifyView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_verify"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED):
            auth_logging.log_token_failure(None, response.status_code)
            response.data = {"detail": "Invalid credentials."}
        return response


class CustomerRegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_register"

    def post(self, request, *args, **kwargs):
        serializer = CustomerRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        auth_logging.log_register_success(user.id, str(user.role))

        return Response(
            {
                "user_id": user.id,
                "role": str(user.role),
            },
            status=status.HTTP_201_CREATED,
        )


class DriverRegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_register"

    def post(self, request, *args, **kwargs):
        serializer = DriverRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        driver_profile = user.driver_profile
        auth_logging.log_register_success(user.id, str(user.role))

        registration_token = issue_onboarding_token(user_id=user.id)

        return Response(
            {
                "id": user.id,
                "phone": user.phone,
                "role": str(user.role),
                "approval_status": driver_profile.approval_status,
                "registration_token": registration_token,
            },
            status=status.HTTP_201_CREATED,
        )


class CreateSalesAgentView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserRole]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_admin_create_sales"

    def post(self, request, *args, **kwargs):
        serializer = SalesAgentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        auth_logging.log_sales_agent_create(request.user.id, user.id, user.phone)

        profile = getattr(user, "sales_profile", None)
        return Response(
            {
                "user_id": user.id,
                "phone": user.phone,
                "name": profile.full_name if profile else "",
                "role": str(user.role),
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(MeSerializer(request.user).data)

    def patch(self, request, *args, **kwargs):
        from apps.users.models import CustomerProfile, User

        user = request.user
        body = CustomerMeUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        if user.role == User.Role.CUSTOMER:
            try:
                profile = user.customer_profile
            except CustomerProfile.DoesNotExist:
                profile = CustomerProfile.objects.create(user=user, full_name="")
            if "full_name" in data:
                profile.full_name = (data["full_name"] or "").strip()
            if "email" in data:
                profile.email = (data["email"] or "").strip()
            profile.save()
        elif user.role in (User.Role.ADMIN, User.Role.SALES):
            if "recovery_email" in data:
                user.recovery_email = (data["recovery_email"] or "").strip()
                user.save(update_fields=["recovery_email"])
        else:
            return Response(
                {"detail": "Profile updates are not available for this role."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(MeSerializer(user).data)


class DeleteAccountView(APIView):
    """POST /api/v1/auth/me/delete — customer and driver self-service deactivation."""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        body = DeleteAccountSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        refresh = body.validated_data.get("refresh") or None

        try:
            delete_own_account(user=request.user, refresh_token=refresh)
        except AccountDeletionError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)
        except Exception:
            return Response(
                {"detail": "Could not delete your account. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        auth_logging.log_account_deleted(
            user_id=request.user.id,
            role=str(request.user.role),
        )
        return Response(
            {"message": "Your account has been deleted."},
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_logout"

    def post(self, request, *args, **kwargs):
        raw = request.data.get("refresh")
        if not raw or not isinstance(raw, str):
            return Response({"detail": "Field 'refresh' is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(raw)
            token.blacklist()
        except TokenError:
            pass
        auth_logging.log_logout(request.user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def test_auth(request):
    return Response(
        {
            "message": "Authenticated",
            "user_id": request.user.id,
            "role": request.user.role,
        }
    )


class StaffOpsCheckView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSales]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_staff"

    def get(self, request, *args, **kwargs):
        return Response(
            {
                "ok": True,
                "user_id": request.user.id,
                "role": request.user.role,
            }
        )


class SalesAgentDetailView(APIView):
    """PATCH /api/v1/auth/sales-agents/{id}/ — update name and/or active status."""

    permission_classes = [IsAuthenticated, IsAdminUserRole]

    def patch(self, request, user_id, *args, **kwargs):
        try:
            user = User.objects.select_related("sales_profile").get(
                id=user_id, role=User.Role.SALES
            )
        except User.DoesNotExist:
            return Response(
                {"detail": "Sales agent not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = SalesAgentUpdateSerializer(instance=user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserListSerializer(user).data)


class AdminUsersListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserRole]

    def get(self, request, *args, **kwargs):
        users = (
            User.objects.all()
            .select_related("customer_profile", "driver_profile", "sales_profile")
            .order_by("-created_at")
        )
        q = (request.query_params.get("q") or "").strip()
        if q:
            users = users.filter(
                Q(phone__icontains=q)
                | Q(customer_profile__full_name__icontains=q)
                | Q(driver_profile__full_name__icontains=q)
                | Q(sales_profile__full_name__icontains=q)
            )
        return Response(UserListSerializer(users, many=True).data)


class CustomerSearchPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 50


class CustomerSearchView(APIView):
    """Search registered customers by phone or name (admin + sales only)."""

    permission_classes = [IsAuthenticated, IsAdminOrSales]

    def get(self, request, *args, **kwargs):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response(
                {"detail": "Query parameter 'q' must be at least 2 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = (
            User.objects.filter(role=User.Role.CUSTOMER, is_active=True)
            .select_related("customer_profile")
            .filter(
                Q(phone__icontains=q)
                | Q(customer_profile__full_name__icontains=q)
            )
            .order_by("-created_at")
        )
        paginator = CustomerSearchPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = CustomerSearchSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
