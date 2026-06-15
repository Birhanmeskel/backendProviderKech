from django.urls import path

from .views import (
    AdminDriverDocumentsView,
    ApprovedDriversListView,
    ApproveDriverView,
    DriverBalancesView,
    PendingDriversListView,
    ReactivateDriverView,
    RejectDriverView,
    SuspendDriverView,
    SuspendedDriversListView,
    UpdateDriverBalanceView,
    UpdateDriverProfileView,
    UpdatePayoutPercentageView,
)

urlpatterns = [
    path("balances/", DriverBalancesView.as_view(), name="admin_drivers_balances"),
    path("approved/", ApprovedDriversListView.as_view(), name="admin_drivers_approved"),
    path("pending/", PendingDriversListView.as_view(), name="admin_drivers_pending"),
    path("suspended/", SuspendedDriversListView.as_view(), name="admin_drivers_suspended"),
    path(
        "<int:user_id>/documents/",
        AdminDriverDocumentsView.as_view(),
        name="admin_driver_documents",
    ),
    path("<int:user_id>/approve/", ApproveDriverView.as_view(), name="admin_driver_approve"),
    path("<int:user_id>/reject/", RejectDriverView.as_view(), name="admin_driver_reject"),
    path("<int:user_id>/suspend/", SuspendDriverView.as_view(), name="admin_driver_suspend"),
    path(
        "<int:user_id>/reactivate/",
        ReactivateDriverView.as_view(),
        name="admin_driver_reactivate",
    ),
    path(
        "<int:user_id>/payout-percentage/",
        UpdatePayoutPercentageView.as_view(),
        name="admin_driver_payout_percentage",
    ),
    path(
        "<int:user_id>/balance/",
        UpdateDriverBalanceView.as_view(),
        name="admin_driver_balance",
    ),
    path(
        "<int:user_id>/",
        UpdateDriverProfileView.as_view(),
        name="admin_driver_update",
    ),
]
