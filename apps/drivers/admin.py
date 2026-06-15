from django.contrib import admin

from .models import DriverDocument, DriverProfile


@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "approval_status",
        "approved_at",
        "rejected_at",
        "suspended_at",
        "created_at",
    )
    list_filter = ("approval_status",)
    search_fields = ("user__phone", "full_name")
    autocomplete_fields = ("user", "approved_by", "reviewed_by")
    readonly_fields = ("created_at", "updated_at")


@admin.register(DriverDocument)
class DriverDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "document_type", "uploaded_at")
    list_filter = ("document_type",)
    search_fields = ("user__phone",)
