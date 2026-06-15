from django.urls import path

from .views import DriverPayoutAnalyticsView, PlatformProfitAnalyticsView, RevenueAnalyticsView

urlpatterns = [
    path("revenue/", RevenueAnalyticsView.as_view(), name="admin_analytics_revenue"),
    path("drivers/", DriverPayoutAnalyticsView.as_view(), name="admin_analytics_drivers"),
    path("platform-profit/", PlatformProfitAnalyticsView.as_view(), name="admin_analytics_platform_profit"),
]
