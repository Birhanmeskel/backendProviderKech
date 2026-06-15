from __future__ import annotations

from datetime import date

from rest_framework import serializers


class AnalyticsFilterSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    def validate(self, attrs):
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({"detail": "start_date must be on or before end_date."})
        return attrs


class DriverAnalyticsFilterSerializer(AnalyticsFilterSerializer):
    driver_id = serializers.IntegerField(required=False, min_value=1)


class DateRangeSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class RevenueTotalsSerializer(serializers.Serializer):
    revenue_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_today = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_weekly = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_monthly = serializers.DecimalField(max_digits=12, decimal_places=2)
    orders_count = serializers.IntegerField()
    successful_payments_count = serializers.IntegerField()


class RevenueTrendPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    orders_count = serializers.IntegerField()


class OrderStatusDistributionSerializer(serializers.Serializer):
    status = serializers.CharField()
    count = serializers.IntegerField()


class TopRestaurantRevenueSerializer(serializers.Serializer):
    restaurant_id = serializers.IntegerField()
    restaurant_name = serializers.CharField()
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    orders_count = serializers.IntegerField()


class RevenueAnalyticsResponseSerializer(serializers.Serializer):
    currency = serializers.CharField()
    date_range = DateRangeSerializer()
    totals = RevenueTotalsSerializer()
    trends = RevenueTrendPointSerializer(many=True)
    order_status_distribution = OrderStatusDistributionSerializer(many=True)
    top_restaurants = TopRestaurantRevenueSerializer(many=True)


class DriverPayoutSummarySerializer(serializers.Serializer):
    total_drivers = serializers.IntegerField()
    total_deliveries = serializers.IntegerField()
    driver_payout_total = serializers.DecimalField(max_digits=12, decimal_places=2)


class DriverPayoutRowSerializer(serializers.Serializer):
    driver_id = serializers.IntegerField()
    driver_phone = serializers.CharField()
    deliveries_count = serializers.IntegerField()
    payout_total = serializers.DecimalField(max_digits=12, decimal_places=2)


class DriverPayoutResponseSerializer(serializers.Serializer):
    currency = serializers.CharField()
    date_range = DateRangeSerializer()
    assumptions = serializers.DictField(child=serializers.CharField())
    summary = DriverPayoutSummarySerializer()
    drivers = DriverPayoutRowSerializer(many=True)


class PlatformProfitTotalsSerializer(serializers.Serializer):
    gross_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    delivery_fee_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    driver_payout_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    platform_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_deliveries = serializers.IntegerField()


class PlatformProfitResponseSerializer(serializers.Serializer):
    currency = serializers.CharField()
    date_range = DateRangeSerializer()
    totals = PlatformProfitTotalsSerializer()
