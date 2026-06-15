"""Order lifecycle and creation (business rules outside views)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order, OrderItem
from apps.orders.services.pricing import (
    DeliveryPricing,
    apply_driver_percentage,
    compute_pricing,
    haversine_km,
)
from apps.restaurants.models import MenuItem, Restaurant
from apps.restaurants.services.hours import restaurant_is_open
from core.models import User

DEFAULT_DELIVERY_FEE = Decimal("25.00")
MAX_ACTIVE_DRIVER_ORDERS = 2

ADMIN_MODIFIABLE_STATUSES = frozenset(
    {
        Order.Status.PENDING,
        Order.Status.CONFIRMED,
        Order.Status.PREPARING,
        Order.Status.READY_FOR_PICKUP,
        Order.Status.ASSIGNED,
        Order.Status.DECLINED,
        Order.Status.PICKED_UP,
        Order.Status.DELIVERING,
    }
)

ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    Order.Status.PENDING: {Order.Status.CONFIRMED, Order.Status.CANCELLED},
    Order.Status.CONFIRMED: {
        Order.Status.SEARCHING_DRIVER,
        Order.Status.PREPARING,
        Order.Status.CANCELLED,
    },
    Order.Status.SEARCHING_DRIVER: {Order.Status.ASSIGNED, Order.Status.CANCELLED},
    Order.Status.PREPARING: {Order.Status.READY_FOR_PICKUP, Order.Status.CANCELLED},
    Order.Status.READY_FOR_PICKUP: {Order.Status.ASSIGNED, Order.Status.CANCELLED},
    Order.Status.ASSIGNED: {
        Order.Status.PICKED_UP,
        Order.Status.CANCELLED,
        Order.Status.DECLINED,
    },
    Order.Status.DECLINED: {Order.Status.CANCELLED, Order.Status.READY_FOR_PICKUP},
    Order.Status.PICKED_UP: {Order.Status.DELIVERING, Order.Status.CANCELLED},
    Order.Status.DELIVERING: {Order.Status.DELIVERED},
    Order.Status.DELIVERED: set(),
    Order.Status.CANCELLED: set(),
}


class OrderServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _generate_reference(order_id: int) -> str:
    return f"KD-{order_id:04d}"


def _coerce_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _validate_delivery_address(address: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(address, dict):
        raise OrderServiceError("delivery_address must be an object.")
    receiver = (address.get("receiver_name") or "").strip()
    phone = (address.get("phone") or "").strip()
    line = (address.get("address_line") or "").strip()
    if not receiver:
        raise OrderServiceError("Receiver name is required.")
    if not phone or len(phone) < 8:
        raise OrderServiceError("A valid delivery phone is required.")
    if not line:
        raise OrderServiceError("Delivery address line is required.")
    cleaned: dict[str, Any] = {
        "receiver_name": receiver,
        "phone": phone,
        "address_line": line,
        "landmark": (address.get("landmark") or "").strip(),
    }
    lat = _coerce_optional_float(address.get("latitude"))
    lon = _coerce_optional_float(address.get("longitude"))
    if lat is not None and lon is not None:
        cleaned["latitude"] = lat
        cleaned["longitude"] = lon
    return cleaned


def _pricing_for(restaurant: Restaurant, address: dict[str, Any]) -> DeliveryPricing:
    """Compute the financial snapshot for a delivery, with fallback when coords missing."""
    dropoff_lat = address.get("latitude")
    dropoff_lon = address.get("longitude")
    restaurant_lat = restaurant.latitude
    restaurant_lon = restaurant.longitude
    if (
        dropoff_lat is None
        or dropoff_lon is None
        or restaurant_lat is None
        or restaurant_lon is None
    ):
        return compute_pricing(None)
    distance_km = haversine_km(restaurant_lat, restaurant_lon, dropoff_lat, dropoff_lon)
    return compute_pricing(distance_km)


@transaction.atomic
def create_order(
    *,
    customer: User,
    restaurant_id: int,
    items: list[dict[str, Any]],
    delivery_address: dict[str, Any],
    customer_note: str = "",
    sales_agent: User | None = None,
    delivery_fee: Decimal | None = None,
    payment_method: str = Order.PaymentMethod.CHAPA,
) -> Order:
    if customer.role != User.Role.CUSTOMER:
        raise OrderServiceError("Orders must be placed for a customer account.", status_code=403)

    try:
        restaurant = Restaurant.objects.get(pk=restaurant_id, is_active=True)
    except Restaurant.DoesNotExist as exc:
        raise OrderServiceError("Restaurant not found or inactive.", status_code=404) from exc

    if not restaurant_is_open(restaurant):
        raise OrderServiceError("Restaurant is currently closed.", status_code=400)

    if not items:
        raise OrderServiceError("At least one menu item is required.")

    validated_address = _validate_delivery_address(delivery_address)
    if delivery_fee is not None:
        # Explicit admin/sales override — keep the breakdown consistent by
        # treating the override as the full delivery_fee and zeroing the
        # platform share. Negative values stay an error.
        if delivery_fee < 0:
            raise OrderServiceError("delivery_fee cannot be negative.")
        pricing = DeliveryPricing(
            distance_km=None,
            driver_payout=delivery_fee,
            platform_fee=Decimal("0.00"),
            delivery_fee=delivery_fee,
        )
    else:
        pricing = _pricing_for(restaurant, validated_address)

    order = Order.objects.create(
        reference="KD-PENDING",
        customer=customer,
        restaurant=restaurant,
        sales_agent=sales_agent if sales_agent and sales_agent.role == User.Role.SALES else None,
        status=Order.Status.PENDING,
        payment_method=payment_method,
        delivery_address=validated_address,
        customer_note=(customer_note or "").strip(),
        delivery_fee=pricing.delivery_fee,
        driver_payout=pricing.driver_payout,
        platform_fee=pricing.platform_fee,
    )
    order.reference = _generate_reference(order.pk)
    order.save(update_fields=["reference"])

    subtotal = Decimal("0.00")
    for line in items:
        menu_item_id = line.get("menu_item_id")
        quantity = int(line.get("quantity") or 0)
        if quantity < 1:
            raise OrderServiceError("Item quantity must be at least 1.")
        try:
            menu_item = MenuItem.objects.select_related("category").get(
                pk=menu_item_id,
                restaurant=restaurant,
                is_available=True,
                category__is_active=True,
            )
        except MenuItem.DoesNotExist as exc:
            raise OrderServiceError(f"Menu item {menu_item_id} is unavailable.", status_code=400) from exc

        unit = menu_item.price
        box_price = menu_item.takeaway_box_price
        line_total = (unit + box_price) * quantity
        subtotal += line_total
        OrderItem.objects.create(
            order=order,
            menu_item=menu_item,
            item_name=menu_item.name,
            quantity=quantity,
            unit_price=unit,
            takeaway_box_price=box_price,
            total_price=line_total,
        )

    order.subtotal = subtotal
    order.total_amount = subtotal + pricing.delivery_fee
    order.save(update_fields=["subtotal", "total_amount", "updated_at"])
    return order


def _replace_order_items(*, order: Order, items: list[dict[str, Any]]) -> Decimal:
    """Replace line items and return new subtotal."""
    if not items:
        raise OrderServiceError("At least one menu item is required.")

    restaurant = order.restaurant
    order.items.all().delete()
    subtotal = Decimal("0.00")
    for line in items:
        menu_item_id = line.get("menu_item_id")
        quantity = int(line.get("quantity") or 0)
        if quantity < 1:
            raise OrderServiceError("Item quantity must be at least 1.")
        try:
            menu_item = MenuItem.objects.select_related("category").get(
                pk=menu_item_id,
                restaurant=restaurant,
                is_available=True,
                category__is_active=True,
            )
        except MenuItem.DoesNotExist as exc:
            raise OrderServiceError(f"Menu item {menu_item_id} is unavailable.", status_code=400) from exc

        unit = menu_item.price
        box_price = menu_item.takeaway_box_price
        line_total = (unit + box_price) * quantity
        subtotal += line_total
        OrderItem.objects.create(
            order=order,
            menu_item=menu_item,
            item_name=menu_item.name,
            quantity=quantity,
            unit_price=unit,
            takeaway_box_price=box_price,
            total_price=line_total,
        )
    return subtotal


@transaction.atomic
def modify_order(
    *,
    order: Order,
    items: list[dict[str, Any]] | None = None,
    delivery_address: dict[str, Any] | None = None,
    customer_note: str | None = None,
) -> Order:
    if order.is_terminal:
        raise OrderServiceError("Delivered or cancelled orders cannot be modified.", status_code=409)

    if order.status not in ADMIN_MODIFIABLE_STATUSES:
        raise OrderServiceError("This order can no longer be modified.", status_code=409)

    update_fields = ["updated_at"]

    if delivery_address is not None:
        validated_address = _validate_delivery_address(delivery_address)
        order.delivery_address = validated_address
        pricing = _pricing_for(order.restaurant, validated_address)
        order.delivery_fee = pricing.delivery_fee
        order.driver_payout = pricing.driver_payout
        order.platform_fee = pricing.platform_fee
        update_fields.extend(["delivery_address", "delivery_fee", "driver_payout", "platform_fee"])

    if customer_note is not None:
        order.customer_note = (customer_note or "").strip()
        update_fields.append("customer_note")

    if items is not None:
        subtotal = _replace_order_items(order=order, items=items)
        order.subtotal = subtotal
        order.total_amount = subtotal + order.delivery_fee
        update_fields.extend(["subtotal", "total_amount"])

    order.updated_at = timezone.now()
    order.save(update_fields=list(dict.fromkeys(update_fields)))
    return order


@transaction.atomic
def transition_order_status(order: Order, new_status: str) -> Order:
    if order.is_terminal:
        raise OrderServiceError("Delivered or cancelled orders cannot be modified.", status_code=409)

    allowed = ALLOWED_STATUS_TRANSITIONS.get(order.status, set())
    if new_status not in allowed:
        raise OrderServiceError(
            f"Cannot transition from {order.status} to {new_status}.",
            status_code=409,
        )

    order.status = new_status
    order.updated_at = timezone.now()
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def mark_order_paid_from_payment(order: Order) -> Order:
    """Mark order paid after Chapa verification (webhook or verify API)."""
    order.refresh_from_db()
    if order.payment_status == Order.PaymentStatus.PAID:
        return order
    if order.payment_status == Order.PaymentStatus.FAILED:
        raise OrderServiceError("Payment has failed for this order.", status_code=409)

    order.payment_status = Order.PaymentStatus.PAID
    order.updated_at = timezone.now()
    order.save(update_fields=["payment_status", "updated_at"])

    if order.status == Order.Status.PENDING:
        order = transition_order_status(order, Order.Status.CONFIRMED)
    # Auto-broadcast: a confirmed, unassigned order should be visible to
    # online approved drivers so the first-accept-wins flow can run.
    if order.status == Order.Status.CONFIRMED and order.assigned_driver_id is None:
        order = transition_order_status(order, Order.Status.SEARCHING_DRIVER)
    return order


ACTIVE_DRIVER_STATUSES = (
    Order.Status.ASSIGNED,
    Order.Status.PICKED_UP,
    Order.Status.DELIVERING,
)


@transaction.atomic
def accept_order(*, order_id: int, driver: User) -> Order:
    """Atomic first-accept-wins. Re-checks driver eligibility under lock."""
    from apps.drivers.models import DriverProfile  # local import avoids cycle

    if driver.role != User.Role.DRIVER:
        raise OrderServiceError("Only drivers can accept orders.", status_code=403)
    try:
        profile = driver.driver_profile
    except DriverProfile.DoesNotExist as exc:
        raise OrderServiceError("Driver profile not found.", status_code=404) from exc
    if profile.approval_status != DriverProfile.ApprovalStatus.APPROVED:
        raise OrderServiceError("Driver is not approved.", status_code=403)
    # OFFLINE blocks accept. BUSY drivers (already on one delivery) can still
    # claim more — up to MAX_ACTIVE_DRIVER_ORDERS below — which mirrors the
    # operator-side rule of "every approved+online driver sees the broadcast".
    if profile.operational_status == DriverProfile.OperationalStatus.OFFLINE:
        raise OrderServiceError("Driver must be online to accept.", status_code=409)
    if not driver.is_active:
        raise OrderServiceError("Driver account is inactive.", status_code=403)

    active_count = Order.objects.filter(
        assigned_driver=driver,
        status__in=ACTIVE_DRIVER_STATUSES,
    ).count()
    if active_count >= MAX_ACTIVE_DRIVER_ORDERS:
        raise OrderServiceError(
            f"Driver already has {MAX_ACTIVE_DRIVER_ORDERS} active deliveries.",
            status_code=409,
        )

    now = timezone.now()
    updated = (
        Order.objects.filter(
            pk=order_id,
            assigned_driver__isnull=True,
            status=Order.Status.SEARCHING_DRIVER,
        )
        .update(
            assigned_driver=driver,
            status=Order.Status.ASSIGNED,
            # Self-claim implies acknowledgement, so the order skips the
            # manual-assignment "Accept / Decline" card on the next poll.
            driver_acknowledged_at=now,
            updated_at=now,
        )
    )
    if updated == 0:
        raise OrderServiceError("Order is no longer available.", status_code=409)

    order = Order.objects.get(pk=order_id)
    driver_payout, platform_fee = apply_driver_percentage(
        order.delivery_fee, profile.payout_percentage,
    )
    order.driver_payout = driver_payout
    order.platform_fee = platform_fee
    order.save(update_fields=["driver_payout", "platform_fee"])
    return order
