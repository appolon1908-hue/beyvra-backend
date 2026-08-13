from django.utils import timezone
from .models import HealthCheckResult, ServiceDefinition


class HealthAuthority:
    @staticmethod
    def latest():
        rows=[]
        for service in ServiceDefinition.objects.filter(status="ACTIVE").order_by("code"):
            result=HealthCheckResult.objects.filter(service_code=service.code).order_by("-observed_at").first()
            rows.append({"service": service.code, "criticality": service.criticality, "health": result.state if result else "UNKNOWN", "latency_ms": str(result.latency_ms) if result else None, "observed_at": result.observed_at if result else None, "failure_reason_safe": result.failure_reason_safe if result else "NOT_OBSERVED"})
        return rows

    @classmethod
    def system_state(cls):
        rows=cls.latest(); critical=[r for r in rows if r["criticality"] in {"TIER_0","TIER_1"}]
        if not critical: return "UNHEALTHY"
        if any(r["health"] in {"UNHEALTHY","UNKNOWN"} for r in critical): return "UNHEALTHY"
        if any(r["health"] != "HEALTHY" for r in rows): return "DEGRADED"
        return "HEALTHY"
