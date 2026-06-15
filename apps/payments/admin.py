from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "chapa_tx_ref",
        "order",
        "customer",
        "amount",
        "currency",
        "status",
        "paid_at",
        "created_at",
    )
    list_filter = ("status", "currency", "payment_method")
    search_fields = ("chapa_tx_ref", "chapa_reference", "order__reference", "customer__phone")
    readonly_fields = (
        "raw_initialize_response",
        "raw_verify_response",
        "raw_webhook_payload",
        "created_at",
        "updated_at",
    )
