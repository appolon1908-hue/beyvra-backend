import time
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from .models import HealthCheckResult, ServiceDefinition


def check_postgres():
    start=time.perf_counter()
    try:
        with connection.cursor() as cursor: cursor.execute("SELECT 1"); ok=cursor.fetchone()[0] == 1
        return ok, (time.perf_counter()-start)*1000, ""
    except Exception: return False, (time.perf_counter()-start)*1000, "DEPENDENCY_UNAVAILABLE"


def check_redis():
    start=time.perf_counter()
    try:
        cache.set("ops:health", "1", 5); ok=cache.get("ops:health") == "1"
        return ok, (time.perf_counter()-start)*1000, ""
    except Exception: return False, (time.perf_counter()-start)*1000, "DEPENDENCY_UNAVAILABLE"


CHECKS = {"postgresql": check_postgres, "redis": check_redis}


def execute_required_checks():
    results=[]
    for service in ServiceDefinition.objects.filter(status="ACTIVE"):
        checker=CHECKS.get(service.code)
        if checker:
            ok, latency, reason=checker()
            results.append(HealthCheckResult.objects.create(service_code=service.code, check_code="canonical", state="HEALTHY" if ok else "UNHEALTHY", latency_ms=latency, observed_at=timezone.now(), failure_reason_safe=reason))
    return results
