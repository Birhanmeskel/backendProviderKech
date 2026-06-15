from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.orders.models import DriverDeliveryEvent, Order


@dataclass(frozen=True)
class AnalyticsDateRange:
    start_dt: datetime
    end_dt: datetime
    start_date: date
    end_date: date


def _aware_start(d: date) -> datetime:
    return timezone.make_aware(datetime.combine(d, time.min), timezone.get_current_timezone())


def _aware_end(d: date) -> datetime:
    return timezone.make_aware(datetime.combine(d, time.max), timezone.get_current_timezone())


def resolve_date_range(*, start_date: date | None, end_date: date | None) -> AnalyticsDateRange:
    today = timezone.localdate()
    resolved_end = end_date or today
    resolved_start = start_date or (resolved_end - timedelta(days=6))
    if resolved_start > resolved_end:
        raise ValueError("start_date must be on or before end_date.")
    return AnalyticsDateRange(
        start_dt=_aware_start(resolved_start),
        end_dt=_aware_end(resolved_end),
        start_date=resolved_start,
        end_date=resolved_end,
    )


def _paid_orders_qs(date_range: AnalyticsDateRange):
    """All orders with payment_status=paid in the date range (covers both
    Chapa payments and sales-agent cash/manual orders)."""
    return Order.objects.filter(
        payment_status=Order.PaymentStatus.PAID,
        placed_at__range=(date_range.start_dt, date_range.end_dt),
    ).select_related("restaurant")


def _paid_orders_revenue(date_range: AnalyticsDateRange) -> Decimal:
    return _paid_orders_qs(date_range).aggregate(
        total=Coalesce(
            Sum("total_amount"),
            Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
        ),
    )["total"]


def revenue_overview(*, date_range: AnalyticsDateRange) -> dict:
    paid_qs = _paid_orders_qs(date_range)

    agg = paid_qs.aggregate(
        revenue_total=Coalesce(
            Sum("total_amount"),
            Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
        ),
    )
    revenue_total = agg["revenue_total"]
    paid_orders_count = paid_qs.count()

    successful_payments_count = paid_orders_count

    today = timezone.localdate()
    this_week_start = today - timedelta(days=today.weekday())
    this_month_start = today.replace(day=1)

    today_total = _paid_orders_revenue(AnalyticsDateRange(
        start_dt=_aware_start(today), end_dt=_aware_end(today),
        start_date=today, end_date=today,
    ))
    weekly_total = _paid_orders_revenue(AnalyticsDateRange(
        start_dt=_aware_start(this_week_start), end_dt=_aware_end(today),
        start_date=this_week_start, end_date=today,
    ))
    monthly_total = _paid_orders_revenue(AnalyticsDateRange(
        start_dt=_aware_start(this_month_start), end_dt=_aware_end(today),
        start_date=this_month_start, end_date=today,
    ))

    trend_seed: OrderedDict[str, dict] = OrderedDict()
    pointer = date_range.start_date
    while pointer <= date_range.end_date:
        trend_seed[pointer.isoformat()] = {
            "date": pointer.isoformat(),
            "revenue": Decimal("0.00"),
            "orders_count": 0,
        }
        pointer += timedelta(days=1)

    trend_rows = (
        paid_qs.annotate(day=TruncDate("placed_at"))
        .values("day")
        .annotate(
            revenue=Coalesce(
                Sum("total_amount"),
                Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
            paid_orders=Count("id"),
        )
        .order_by("day")
    )
    trend_index = {k: v for k, v in trend_seed.items()}
    for row in trend_rows:
        key = row["day"].isoformat()
        trend_index[key] = {
            "date": key,
            "revenue": row["revenue"],
            "orders_count": row["paid_orders"],
        }
    trend = list(trend_index.values())

    status_distribution_rows = (
        Order.objects.filter(
            placed_at__range=(date_range.start_dt, date_range.end_dt),
        )
        .values("status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    top_restaurants = (
        paid_qs.values("restaurant_id", "restaurant__name")
        .annotate(
            revenue=Coalesce(
                Sum("total_amount"),
                Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
            orders_count=Count("id"),
        )
        .order_by("-revenue", "-orders_count")[:10]
    )

    return {
        "currency": "ETB",
        "date_range": {"start_date": date_range.start_date, "end_date": date_range.end_date},
        "totals": {
            "revenue_total": revenue_total,
            "revenue_today": today_total,
            "revenue_weekly": weekly_total,
            "revenue_monthly": monthly_total,
            "orders_count": paid_orders_count,
            "successful_payments_count": successful_payments_count,
        },
        "trends": trend,
        "order_status_distribution": [
            {
                "status": row["status"],
                "count": row["count"],
            }
            for row in status_distribution_rows
        ],
        "top_restaurants": [
            {
                "restaurant_id": row["restaurant_id"],
                "restaurant_name": row["restaurant__name"] or "Unknown",
                "revenue": row["revenue"],
                "orders_count": row["orders_count"],
            }
            for row in top_restaurants
        ],
    }


def driver_payout_report(*, date_range: AnalyticsDateRange, driver_id: int | None = None) -> dict:
    completed_events = DriverDeliveryEvent.objects.filter(
        action=DriverDeliveryEvent.Action.COMPLETED,
        created_at__range=(date_range.start_dt, date_range.end_dt),
        order__status=Order.Status.DELIVERED,
        order__assigned_driver__isnull=False,
    ).select_related("order", "driver")

    if driver_id is not None:
        completed_events = completed_events.filter(driver_id=driver_id)

    rows = (
        completed_events.values("driver_id", "driver__phone")
        .annotate(
            deliveries_count=Count("order_id", distinct=True),
            payout_total=Coalesce(
                Sum("order__driver_payout"),
                Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
        )
        .order_by("-payout_total", "-deliveries_count")
    )

    summary = completed_events.aggregate(
        total_drivers=Count("driver_id", distinct=True),
        total_deliveries=Count("order_id", distinct=True),
        payout_total=Coalesce(
            Sum("order__driver_payout"),
            Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
        ),
    )

    return {
        "currency": "ETB",
        "date_range": {"start_date": date_range.start_date, "end_date": date_range.end_date},
        "assumptions": {
            "driver_payout_formula": "driver_payout from delivered orders (percentage-based)",
        },
        "summary": {
            "total_drivers": summary["total_drivers"] or 0,
            "total_deliveries": summary["total_deliveries"] or 0,
            "driver_payout_total": summary["payout_total"],
        },
        "drivers": [
            {
                "driver_id": row["driver_id"],
                "driver_phone": row["driver__phone"] or "",
                "deliveries_count": row["deliveries_count"],
                "payout_total": row["payout_total"],
            }
            for row in rows
        ],
    }


def platform_profit_report(*, date_range: AnalyticsDateRange) -> dict:
    paid_orders = _paid_orders_qs(date_range)
    payout_data = driver_payout_report(date_range=date_range)

    gross_revenue = paid_orders.aggregate(
        total=Coalesce(
            Sum("total_amount"),
            Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
        ),
    )["total"]

    driver_payout_total = payout_data["summary"]["driver_payout_total"]

    delivered_orders = Order.objects.filter(
        status=Order.Status.DELIVERED,
        placed_at__range=(date_range.start_dt, date_range.end_dt),
    )

    platform_totals = delivered_orders.aggregate(
        platform_fee_total=Coalesce(
            Sum("platform_fee"),
            Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
        ),
        delivery_fee_total=Coalesce(
            Sum("delivery_fee"),
            Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
        ),
    )

    platform_balance = platform_totals["platform_fee_total"]
    delivery_fee_total = platform_totals["delivery_fee_total"]

    return {
        "currency": "ETB",
        "date_range": {"start_date": date_range.start_date, "end_date": date_range.end_date},
        "totals": {
            "gross_revenue": gross_revenue,
            "delivery_fee_total": delivery_fee_total,
            "driver_payout_total": driver_payout_total,
            "platform_balance": platform_balance,
            "total_deliveries": payout_data["summary"]["total_deliveries"],
        },
    }
