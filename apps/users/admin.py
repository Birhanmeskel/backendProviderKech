from django.contrib import admin

from .models import CustomerProfile


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "full_name", "created_at")
    search_fields = ("user__phone", "full_name")
    autocomplete_fields = ("user",)
