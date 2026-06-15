from django.urls import path

from .views import (
    AssignDriverView,
    ConfirmPaymentView,
    DeliveryFeeQuoteView,
    DriverOrdersListView,
    MyOrdersListView,
    OrderDetailView,
    OrderListCreateView,
    OrderModifyView,
    OrderStatusUpdateView,
)

urlpatterns = [
    path("", OrderListCreateView.as_view()),
    path("my/", MyOrdersListView.as_view()),
    path("quote-delivery-fee/", DeliveryFeeQuoteView.as_view()),
    path("<int:order_id>/", OrderDetailView.as_view()),
    path("<int:order_id>/confirm-payment/", ConfirmPaymentView.as_view()),
    path("<int:order_id>/status/", OrderStatusUpdateView.as_view()),
    path("<int:order_id>/modify/", OrderModifyView.as_view()),
    path("<int:order_id>/assign-driver/", AssignDriverView.as_view()),
]

driver_order_urls = [
    path("orders/", DriverOrdersListView.as_view()),
]
