"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from core.health_views import health, ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health),
    path("ready", ready),
    path("api/v1/auth/", include("apps.users.api.urls")),
    path("api/v1/admin/drivers/", include("apps.drivers.api.admin_urls")),
    path("api/v1/admin/analytics/", include("apps.analytics.api.urls")),
    path("api/v1/drivers/", include("apps.drivers.api.urls")),
    path("api/v1/restaurants/", include("apps.restaurants.api.urls")),
    path("api/v1/orders/", include("apps.orders.api.urls")),
    path("api/v1/payments/", include("apps.payments.api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [
        path(
            "api/schema/",
            SpectacularAPIView.as_view(
                authentication_classes=[],
                permission_classes=[AllowAny],
            ),
            name="schema",
        ),
        path(
            "api/docs/",
            SpectacularSwaggerView.as_view(
                url_name="schema",
                authentication_classes=[],
                permission_classes=[AllowAny],
            ),
            name="swagger-ui",
        ),
    ]
