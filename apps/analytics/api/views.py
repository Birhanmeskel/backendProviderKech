from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.api.serializers import (
    AnalyticsFilterSerializer,
    DriverAnalyticsFilterSerializer,
    DriverPayoutResponseSerializer,
    PlatformProfitResponseSerializer,
    RevenueAnalyticsResponseSerializer,
)
from apps.analytics.services.reporting import (
    driver_payout_report,
    platform_profit_report,
    resolve_date_range,
    revenue_overview,
)
from apps.users.permissions import IsAdminUserRole

logger = logging.getLogger("kech.analytics.api")


class AnalyticsDriverPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class RevenueAnalyticsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserRole]

    def get(self, request, *args, **kwargs):
        filters = AnalyticsFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        try:
            date_range = resolve_date_range(
                start_date=filters.validated_data.get("start_date"),
                end_date=filters.validated_data.get("end_date"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = revenue_overview(date_range=date_range)
        return Response(RevenueAnalyticsResponseSerializer(payload).data)


class DriverPayoutAnalyticsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserRole]

    def get(self, request, *args, **kwargs):
        filters = DriverAnalyticsFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        try:
            date_range = resolve_date_range(
                start_date=filters.validated_data.get("start_date"),
                end_date=filters.validated_data.get("end_date"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = driver_payout_report(
            date_range=date_range,
            driver_id=filters.validated_data.get("driver_id"),
        )

        paginator = AnalyticsDriverPagination()
        page = paginator.paginate_queryset(payload["drivers"], request)
        payload["drivers"] = page if page is not None else payload["drivers"]
        response_data = DriverPayoutResponseSerializer(payload).data
        if page is not None:
            page_response = paginator.get_paginated_response(response_data["drivers"]).data
            response_data["drivers"] = page_response["results"]
            response_data["drivers_pagination"] = {
                "count": page_response["count"],
                "next": page_response["next"],
                "previous": page_response["previous"],
            }
        return Response(response_data)


class PlatformProfitAnalyticsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUserRole]

    def get(self, request, *args, **kwargs):
        filters = AnalyticsFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        try:
            date_range = resolve_date_range(
                start_date=filters.validated_data.get("start_date"),
                end_date=filters.validated_data.get("end_date"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = platform_profit_report(date_range=date_range)
        logger.info(
            "Platform profit analytics requested",
            extra={
                "start_date": date_range.start_date.isoformat(),
                "end_date": date_range.end_date.isoformat(),
                "user_id": request.user.id,
            },
        )
        return Response(PlatformProfitResponseSerializer(payload).data)
