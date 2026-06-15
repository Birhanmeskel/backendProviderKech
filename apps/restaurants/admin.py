from django.contrib import admin

from .models import MenuCategory, MenuItem, Restaurant


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "phone", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "address_text", "phone")


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "restaurant", "name", "sort_order", "is_active")
    list_filter = ("restaurant", "is_active")


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("id", "restaurant", "category", "name", "price", "is_available")
    list_filter = ("restaurant", "is_available")
