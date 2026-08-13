from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def live(_request):
    return JsonResponse({"status": "live"})


@require_GET
def ready(_request):
    checks = {"postgresql": False, "redis": False, "nats": "disabled"}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["postgresql"] = cursor.fetchone()[0] == 1
    except Exception:
        pass
    try:
        cache.set("health:ready", "1", 5)
        checks["redis"] = cache.get("health:ready") == "1"
    except Exception:
        pass
    if settings.NATS_JETSTREAM_ENABLED:
        checks["nats"] = "ready" if cache.get("health:outbox-worker") else "worker_unavailable"
    status = 200 if checks["postgresql"] and checks["redis"] and checks["nats"] in {"disabled", "ready"} else 503
    # Dependency names and topology stay internal; the public contract exposes
    # only the aggregate readiness decision.
    return JsonResponse({"status": "ready" if status == 200 else "not_ready"}, status=status)
