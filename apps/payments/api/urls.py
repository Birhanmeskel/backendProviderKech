from django.urls import path

from .views import (
    ChapaCallbackView,
    ChapaReturnRedirectView,
    ChapaWebhookView,
    MockChapaCheckoutView,
    PaymentDetailView,
    PaymentInitView,
    PaymentListView,
    PaymentVerifyView,
)

urlpatterns = [
    path("init/", PaymentInitView.as_view()),
    path("verify/", PaymentVerifyView.as_view()),
    path("mock-checkout/", MockChapaCheckoutView.as_view()),
    path("return/chapa/", ChapaReturnRedirectView.as_view()),
    path("callback/chapa/", ChapaCallbackView.as_view()),
    path("webhook/chapa/", ChapaWebhookView.as_view()),
    path("", PaymentListView.as_view()),
    path("<int:payment_id>/", PaymentDetailView.as_view()),
]
