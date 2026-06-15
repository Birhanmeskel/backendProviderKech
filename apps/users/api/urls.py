from django.conf import settings
from django.urls import path

from .otp_views import DriverOnboardingOtpSendView, DriverOnboardingOtpVerifyView
from .password_reset_views import PasswordResetConfirmView, PasswordResetRequestView
from .views import (
    AdminUsersListView,
    CreateSalesAgentView,
    CustomerRegisterView,
    CustomerSearchView,
    DeleteAccountView,
    DriverRegisterView,
    LogoutView,
    MeView,
    PhoneTokenObtainPairView,
    RestrictedTokenRefreshView,
    SalesAgentDetailView,
    StaffOpsCheckView,
    ThrottledTokenVerifyView,
    test_auth,
)

urlpatterns = [
    path(
        "password-reset/request/",
        PasswordResetRequestView.as_view(),
        name="password_reset_request",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("token/", PhoneTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", RestrictedTokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", ThrottledTokenVerifyView.as_view(), name="token_verify"),
    path(
        "register/customer",
        CustomerRegisterView.as_view(),
        name="register_customer",
    ),
    path(
        "register/driver",
        DriverRegisterView.as_view(),
        name="register_driver",
    ),
    path("otp/driver/send/", DriverOnboardingOtpSendView.as_view(), name="driver_otp_send"),
    path("otp/driver/verify/", DriverOnboardingOtpVerifyView.as_view(), name="driver_otp_verify"),
    path(
        "create-sales-agent/",
        CreateSalesAgentView.as_view(),
        name="create_sales_agent",
    ),
    path(
        "sales-agents/<int:user_id>/",
        SalesAgentDetailView.as_view(),
        name="sales_agent_detail",
    ),
    path(
        "users/",
        AdminUsersListView.as_view(),
        name="admin_users_list",
    ),
    path(
        "customers/search/",
        CustomerSearchView.as_view(),
        name="customer_search",
    ),
    path("logout", LogoutView.as_view(), name="logout"),
    path("me", MeView.as_view(), name="me"),
    path("me/delete", DeleteAccountView.as_view(), name="me_delete"),
    path("me/delete/", DeleteAccountView.as_view(), name="me_delete_slash"),
    path("staff/ops-check", StaffOpsCheckView.as_view(), name="staff_ops_check"),
]

if settings.DEBUG:
    urlpatterns.append(path("test-auth", test_auth, name="test_auth"))
