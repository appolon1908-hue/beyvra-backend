from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.permissions import IsSreViewer
from .checks import check_postgres, check_redis, execute_required_checks, identity_email_readiness_checks
from .models import ServiceDefinition
from .services import HealthAuthority


def live(_request): return JsonResponse({"status": "live"})


def ready(_request):
    pg=check_postgres(); redis=check_redis(); nats=(not settings.NATS_JETSTREAM_ENABLED) or bool(cache.get("health:outbox-worker")); identity_email=identity_email_readiness_checks(); ok=pg[0] and redis[0] and nats and all(item["ok"] for item in identity_email.values())
    return JsonResponse({"status": "ready" if ok else "not_ready", "checks": {"postgresql": pg[0], "redis": redis[0], "nats": "disabled" if not settings.NATS_JETSTREAM_ENABLED else ("ready" if nats else "worker_unavailable"), **identity_email}}, status=200 if ok else 503)


class SystemStatusView(APIView):
    permission_classes=(AllowAny,)
    def get(self, request):
        state=HealthAuthority.system_state()
        return Response({"system_state": state, "market_data_state": "UNAVAILABLE" if state=="UNHEALTHY" else "DEGRADED", "trading_simulation_state": "AVAILABLE" if state in {"HEALTHY","DEGRADED"} else "UNAVAILABLE", "realtime_state": "AVAILABLE" if settings.REALTIME_V2_ENABLED else "DISABLED", "maintenance_state": state != "HEALTHY"})


class CapabilitiesView(APIView):
    permission_classes=(AllowAny,)
    def get(self, request):
        return Response({"simulation": bool(settings.SIMULATED_TRADING_ENABLED), "market_data": True, "realtime": bool(settings.REALTIME_V2_ENABLED), "reports": True, "real_trading": False, "real_money": False})


class OperatorHealthView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self, request): execute_required_checks(); return Response({"services": HealthAuthority.latest(), "system_state": HealthAuthority.system_state()})


class OperatorDependenciesView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self, request):
        return Response({"dependencies": [{"service": s.code, **{"dependency": d.dependency_code, "required_for_readiness": d.required_for_readiness, "required_for_writes": d.required_for_writes, "failure_mode": d.failure_mode, "timeout_ms": d.timeout_ms}} for s in ServiceDefinition.objects.prefetch_related("dependencies").all() for d in s.dependencies.all()]})
