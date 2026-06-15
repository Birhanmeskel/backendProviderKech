"""
Liveness and readiness probes (architecture: /health and /ready).

- /health: process is up (no dependency checks).
- /ready: database (and optionally Redis) reachable.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
def health(_request):
    return JsonResponse({"status": "ok"})


@require_GET
def ready(_request):
    checks: dict[str, str] = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001 — probe must not leak internals
        logger.warning("Readiness DB check failed: %s", exc)
        checks["database"] = "down"
        return JsonResponse({"status": "not_ready", "checks": checks}, status=503)

    checks["database"] = "ok"

    broker_url = getattr(settings, "CELERY_BROKER_URL", "") or ""
    if broker_url and broker_url.startswith("redis") and getattr(
        settings, "READINESS_CHECK_REDIS", True
    ):
        try:
            import redis

            client = redis.from_url(broker_url, socket_connect_timeout=2)
            client.ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Readiness Redis check failed: %s", exc)
            checks["redis"] = "down"
            return JsonResponse({"status": "not_ready", "checks": checks}, status=503)

    return JsonResponse({"status": "ready", "checks": checks})
