from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.orders.models import Order, OrderItem
from apps.orders.services.pricing import apply_driver_percentage
from core.models import User


class _PayoutOverrideMixin:
    """Override driver_payout/platform_fee for unassigned orders using the
    requesting driver's payout_percentage. Once a driver is assigned, the
    stored values are the source of truth."""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        pct = self.context.get("driver_payout_percentage")
        if pct is not None and instance.assigned_driver_id is None:
            delivery_fee = Decimal(str(data["delivery_fee"]))
            payout, fee = apply_driver_percentage(delivery_fee, pct)
            data["driver_payout"] = str(payout)
            data["platform_fee"] = str(fee)
        return data


class DeliveryAddressSerializer(serializers.Serializer):
    receiver_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=32)
    address_line = serializers.CharField(max_length=500)
    landmark = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)


class OrderItemInputSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    restaurant_id = serializers.IntegerField()
    items = OrderItemInputSerializer(many=True)
    delivery_address = DeliveryAddressSerializer()
    customer_note = serializers.CharField(required=False, allow_blank=True, default="")
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    payment_method = serializers.ChoiceField(
        choices=Order.PaymentMethod.choices,
        required=False,
        default=Order.PaymentMethod.CHAPA,
    )


class SalesOrderCreateSerializer(OrderCreateSerializer):
    customer_id = serializers.IntegerField()
    payment_status = serializers.ChoiceField(
        choices=Order.PaymentStatus.choices,
        required=False,
    )


class OrderItemSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "menu_item",
            "item_name",
            "quantity",
            "unit_price",
            "takeaway_box_price",
            "total_price",
            "image_url",
        )

    def get_image_url(self, obj: OrderItem) -> str | None:
        request = self.context.get("request")
        image = getattr(obj.menu_item, "image", None)
        if not image:
            return None
        url = image.url
        if request:
            return request.build_absolute_uri(url)
        return url


def _sales_agent_display_name(agent: User | None) -> str | None:
    if agent is None:
        return None
    profile = getattr(agent, "sales_profile", None)
    if profile and profile.full_name:
        return profile.full_name
    return agent.phone


def _restaurant_coord(restaurant, field: str) -> float | None:
    value = getattr(restaurant, field, None)
    if value is None:
        return None
    return float(value)


class OrderListSerializer(_PayoutOverrideMixin, serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    restaurant_address = serializers.CharField(source="restaurant.address_text", read_only=True)
    restaurant_latitude = serializers.SerializerMethodField()
    restaurant_longitude = serializers.SerializerMethodField()
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    customer_name = serializers.SerializerMethodField()
    assigned_driver_name = serializers.SerializerMethodField()
    sales_agent_name = serializers.SerializerMethodField()
    order_channel = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "reference",
            "restaurant",
            "restaurant_name",
            "restaurant_address",
            "restaurant_latitude",
            "restaurant_longitude",
            "customer_phone",
            "customer_name",
            "sales_agent",
            "sales_agent_name",
            "order_channel",
            "assigned_driver",
            "assigned_driver_name",
            "status",
            "payment_status",
            "payment_method",
            "subtotal",
            "delivery_fee",
            "driver_payout",
            "platform_fee",
            "total_amount",
            "delivery_address",
            "driver_acknowledged_at",
            "placed_at",
            "updated_at",
            "item_count",
        )

    def get_restaurant_latitude(self, obj: Order) -> float | None:
        return _restaurant_coord(obj.restaurant, "latitude")

    def get_restaurant_longitude(self, obj: Order) -> float | None:
        return _restaurant_coord(obj.restaurant, "longitude")

    def get_customer_name(self, obj: Order) -> str:
        profile = getattr(obj.customer, "customer_profile", None)
        if profile and profile.full_name:
            return profile.full_name
        return obj.customer.phone

    def get_assigned_driver_name(self, obj: Order) -> str | None:
        driver = obj.assigned_driver
        if not driver:
            return None
        profile = getattr(driver, "driver_profile", None)
        if profile and profile.full_name:
            return profile.full_name
        return driver.phone

    def get_sales_agent_name(self, obj: Order) -> str | None:
        return _sales_agent_display_name(obj.sales_agent)

    def get_order_channel(self, obj: Order) -> str:
        return "sales" if obj.sales_agent_id else "app"


class OrderDetailSerializer(_PayoutOverrideMixin, serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    restaurant_address = serializers.CharField(source="restaurant.address_text", read_only=True)
    restaurant_latitude = serializers.SerializerMethodField()
    restaurant_longitude = serializers.SerializerMethodField()
    items = OrderItemSerializer(many=True, read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    sales_agent_name = serializers.SerializerMethodField()
    order_channel = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "reference",
            "customer",
            "customer_phone",
            "restaurant",
            "restaurant_name",
            "restaurant_address",
            "restaurant_latitude",
            "restaurant_longitude",
            "sales_agent",
            "sales_agent_name",
            "order_channel",
            "assigned_driver",
            "status",
            "payment_status",
            "payment_method",
            "subtotal",
            "delivery_fee",
            "driver_payout",
            "platform_fee",
            "total_amount",
            "delivery_address",
            "customer_note",
            "driver_acknowledged_at",
            "placed_at",
            "updated_at",
            "items",
        )

    def get_restaurant_latitude(self, obj: Order) -> float | None:
        return _restaurant_coord(obj.restaurant, "latitude")

    def get_restaurant_longitude(self, obj: Order) -> float | None:
        return _restaurant_coord(obj.restaurant, "longitude")

    def get_sales_agent_name(self, obj: Order) -> str | None:
        return _sales_agent_display_name(obj.sales_agent)

    def get_order_channel(self, obj: Order) -> str:
        return "sales" if obj.sales_agent_id else "app"


class OrderModifySerializer(serializers.Serializer):
    items = OrderItemInputSerializer(many=True, required=False)
    delivery_address = DeliveryAddressSerializer(required=False)
    customer_note = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not any(key in attrs for key in ("items", "delivery_address", "customer_note")):
            raise serializers.ValidationError("Provide at least one field to modify.")
        return attrs


class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)


class AssignDriverSerializer(serializers.Serializer):
    driver_id = serializers.IntegerField()


class DeliveryFeeQuoteInputSerializer(serializers.Serializer):
    restaurant_id = serializers.IntegerField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
