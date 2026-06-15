from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.restaurants.models import MenuCategory, MenuItem, Restaurant
from apps.restaurants.services.hours import restaurant_is_open
from core.currency import DEFAULT_CURRENCY


def _absolute_media_url(request, file_field) -> str | None:
    if not file_field:
        return None
    try:
        url = file_field.url
    except (OSError, ValueError):
        return None
    if request is not None:
        return request.build_absolute_uri(url)
    return url


class RestaurantListSerializer(serializers.ModelSerializer):
    menu_item_count = serializers.IntegerField(read_only=True)
    logo_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    is_open = serializers.SerializerMethodField()
    opens_at = serializers.TimeField(format="%H:%M", required=False, allow_null=True)
    closes_at = serializers.TimeField(format="%H:%M", required=False, allow_null=True)

    class Meta:
        model = Restaurant
        fields = (
            "id",
            "name",
            "description",
            "phone",
            "address_text",
            "latitude",
            "longitude",
            "opens_at",
            "closes_at",
            "opening_hours",
            "is_active",
            "is_open",
            "logo_url",
            "cover_image_url",
            "menu_item_count",
            "updated_at",
        )

    def get_is_open(self, obj: Restaurant) -> bool:
        return restaurant_is_open(obj)

    def get_logo_url(self, obj: Restaurant) -> str | None:
        return _absolute_media_url(self.context.get("request"), obj.logo)

    def get_cover_image_url(self, obj: Restaurant) -> str | None:
        return _absolute_media_url(self.context.get("request"), obj.cover_image)


class RestaurantWriteSerializer(serializers.ModelSerializer):
    """Accepts JSON or multipart (admin logo/cover uploads)."""

    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = Restaurant
        fields = (
            "name",
            "description",
            "phone",
            "address_text",
            "latitude",
            "longitude",
            "opens_at",
            "closes_at",
            "opening_hours",
            "is_active",
            "logo",
            "cover_image",
        )


class MenuCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCategory
        fields = ("id", "name", "sort_order", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = (
            "id",
            "category_id",
            "category_name",
            "name",
            "description",
            "price",
            "takeaway_box_price",
            "currency",
            "is_available",
            "image_url",
            "sort_order",
            "updated_at",
        )
        read_only_fields = ("id", "category_name", "image_url", "updated_at")

    def get_image_url(self, obj: MenuItem) -> str | None:
        return _absolute_media_url(self.context.get("request"), obj.image)


class MenuItemWriteSerializer(serializers.ModelSerializer):
    category_id = serializers.IntegerField()
    currency = serializers.CharField(required=False, default=DEFAULT_CURRENCY, max_length=8)
    is_available = serializers.BooleanField(required=False, default=True)
    takeaway_box_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        default=Decimal("0.00"),
    )

    class Meta:
        model = MenuItem
        fields = (
            "category_id",
            "name",
            "description",
            "price",
            "takeaway_box_price",
            "currency",
            "is_available",
            "image",
            "sort_order",
        )


class PublicMenuItemSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = (
            "id",
            "name",
            "description",
            "price",
            "takeaway_box_price",
            "currency",
            "image_url",
            "sort_order",
        )

    def get_image_url(self, obj: MenuItem) -> str | None:
        return _absolute_media_url(self.context.get("request"), obj.image)


class PublicCatalogItemSerializer(serializers.ModelSerializer):
    """A menu item enriched with its restaurant, for the cross-restaurant
    category browse on the customer home."""

    image_url = serializers.SerializerMethodField()
    restaurant_id = serializers.IntegerField(source="restaurant.id", read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = MenuItem
        fields = (
            "id",
            "name",
            "description",
            "price",
            "takeaway_box_price",
            "currency",
            "image_url",
            "restaurant_id",
            "restaurant_name",
            "category_name",
        )

    def get_image_url(self, obj: MenuItem) -> str | None:
        return _absolute_media_url(self.context.get("request"), obj.image)


class PublicMenuCategorySerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    class Meta:
        model = MenuCategory
        fields = ("id", "name", "sort_order", "items")

    def get_items(self, obj: MenuCategory) -> list:
        items = getattr(obj, "active_items", None)
        if items is None:
            items = obj.items.filter(is_available=True).order_by("sort_order", "name")
        return PublicMenuItemSerializer(items, many=True, context=self.context).data


class RestaurantMenuSerializer(serializers.Serializer):
    restaurant_id = serializers.IntegerField()
    restaurant_name = serializers.CharField()
    categories = PublicMenuCategorySerializer(many=True)
