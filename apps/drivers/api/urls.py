from django.urls import path

from .onboarding_views import (
    DriverDocumentUploadView,
    DriverOnboardingStatusView,
    DriverRequiredDocumentsView,
)
from apps.orders.api.views import (
    AcceptOrderView,
    AvailableOrderDetailView,
    AvailableOrdersListView,
    DriverOrdersListView,
)

from .delivery_views import (
    DriverAvailabilityView,
    DriverOrderAcceptView,
    DriverOrderDeclineView,
    DriverOrderCompleteView,
    DriverOrderDetailView,
    DriverOrderPickupView,
    DriverOrderStartDeliveryView,
)
from .views import DriverStatusView, MyBalanceView

urlpatterns = [
    path("orders/", DriverOrdersListView.as_view(), name="driver_orders"),
    path("orders/available/", AvailableOrdersListView.as_view(), name="driver_orders_available"),
    path(
        "orders/available/<int:order_id>/",
        AvailableOrderDetailView.as_view(),
        name="driver_order_available_detail",
    ),
    path("orders/<int:order_id>/claim/", AcceptOrderView.as_view(), name="driver_order_claim"),
    path("orders/<int:order_id>/", DriverOrderDetailView.as_view(), name="driver_order_detail"),
    path("orders/<int:order_id>/accept/", DriverOrderAcceptView.as_view(), name="driver_order_accept"),
    path("orders/<int:order_id>/decline/", DriverOrderDeclineView.as_view(), name="driver_order_decline"),
    path("orders/<int:order_id>/pickup/", DriverOrderPickupView.as_view(), name="driver_order_pickup"),
    path(
        "orders/<int:order_id>/start-delivery/",
        DriverOrderStartDeliveryView.as_view(),
        name="driver_order_start_delivery",
    ),
    path("orders/<int:order_id>/complete/", DriverOrderCompleteView.as_view(), name="driver_order_complete"),
    path("me/availability/", DriverAvailabilityView.as_view(), name="driver_availability"),
    path("me/status/", DriverStatusView.as_view(), name="driver_me_status"),
    path("me/balance/", MyBalanceView.as_view(), name="driver_me_balance"),
    path("onboarding/status/", DriverOnboardingStatusView.as_view(), name="driver_onboarding_status"),
    path("onboarding/documents/", DriverDocumentUploadView.as_view(), name="driver_onboarding_documents"),
    path(
        "onboarding/documents/required/",
        DriverRequiredDocumentsView.as_view(),
        name="driver_onboarding_documents_required",
    ),
]
