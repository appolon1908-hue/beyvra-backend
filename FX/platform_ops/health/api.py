import os
import re

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from platform_ops.permissions import IsSreViewer

from .checks import check_postgres, check_redis, execute_required_checks
from .models import ServiceDefinition
from .services import HealthAuthority

_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_DIGEST = re.compile(
    r"^(?:[a-z0-9][a-z0-9._/-]*@)?sha256:[0-9a-f]{64}$"
)


def _env_true(name):
    return os.getenv(name, "false").strip().lower() == "true"


def live(_request):
    return JsonResponse({"status": "live"})


def ready(_request):
    pg = check_postgres()
    redis = check_redis()
    nats = (
        not settings.NATS_JETSTREAM_ENABLED
        or bool(cache.get("health:outbox-worker"))
    )
    ok = pg[0] and redis[0] and nats
    return JsonResponse(
        {
            "status": "ready" if ok else "not_ready",
            "checks": {
                "postgresql": pg[0],
                "redis": redis[0],
                "nats": (
                    "disabled"
                    if not settings.NATS_JETSTREAM_ENABLED
                    else ("ready" if nats else "worker_unavailable")
                ),
            },
        },
        status=200 if ok else 503,
    )


class SystemStatusView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        state = HealthAuthority.system_state()
        return Response(
            {
                "system_state": state,
                "market_data_state": (
                    "UNAVAILABLE" if state == "UNHEALTHY" else "DEGRADED"
                ),
                "trading_simulation_state": (
                    "AVAILABLE"
                    if state in {"HEALTHY", "DEGRADED"}
                    else "UNAVAILABLE"
                ),
                "realtime_state": (
                    "AVAILABLE" if settings.REALTIME_V2_ENABLED else "DISABLED"
                ),
                "maintenance_state": state != "HEALTHY",
                "deployment_read_only": _env_true("DEPLOYMENT_READ_ONLY"),
            }
        )


class CapabilitiesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response(
            {
                "simulation": bool(settings.SIMULATED_TRADING_ENABLED),
                "market_data": True,
                "realtime": bool(settings.REALTIME_V2_ENABLED),
                "reports": True,
                "real_trading": False,
                "real_money": False,
                "deployment_read_only": _env_true("DEPLOYMENT_READ_ONLY"),
            }
        )


class ReleaseIdentityView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        source_sha = str(getattr(settings, "RELEASE_SHA", "")).strip()
        image_digest = os.getenv("BEYVRA_IMAGE_DIGEST", "").strip()
        deployment_read_only = _env_true("DEPLOYMENT_READ_ONLY")
        identity = {
            "service": "beyvra-backend",
            "source_repository": os.getenv(
                "BEYVRA_SOURCE_REPOSITORY",
                "https://github.com/appolon1908-hue/beyvra-backend",
            ),
            "source_sha": source_sha or "unknown",
            "image_digest": image_digest or "unknown",
            "release_id": os.getenv("BEYVRA_RELEASE_ID", "").strip()
            or source_sha
            or "unknown",
            "built_at": os.getenv("BEYVRA_BUILD_TIMESTAMP", "").strip()
            or "unknown",
            "deployment_environment": settings.DEPLOYMENT_ENV,
            "deployment_read_only": deployment_read_only,
            "immutable_identity_verified": bool(
                _SOURCE_SHA.fullmatch(source_sha)
                and _IMAGE_DIGEST.fullmatch(image_digest)
            ),
            "safety": {
                "simulation_enabled": bool(
                    settings.SIMULATED_TRADING_ENABLED
                ),
                "live_trading_enabled": bool(
                    getattr(settings, "LIVE_TRADING_ENABLED", False)
                ),
                "real_trading_enabled": bool(
                    getattr(settings, "REAL_TRADING_ENABLED", False)
                ),
                "real_money_enabled": bool(
                    getattr(settings, "REAL_MONEY_ENABLED", False)
                ),
                "external_execution_enabled": bool(
                    getattr(settings, "EXTERNAL_EXECUTION_ENABLED", False)
                ),
                "deployment_read_only": deployment_read_only,
            },
        }
        response = Response(identity)
        response["Cache-Control"] = "no-store"
        return response


class OperatorHealthView(APIView):
    permission_classes = (IsSreViewer,)

    def get(self, request):
        execute_required_checks()
        return Response(
            {
                "services": HealthAuthority.latest(),
                "system_state": HealthAuthority.system_state(),
            }
        )


class OperatorDependenciesView(APIView):
    permission_classes = (IsSreViewer,)

    def get(self, request):
        return Response(
            {
                "dependencies": [
                    {
                        "service": service.code,
                        "dependency": dependency.dependency_code,
                        "required_for_readiness": (
                            dependency.required_for_readiness
                        ),
                        "required_for_writes": dependency.required_for_writes,
                        "failure_mode": dependency.failure_mode,
                        "timeout_ms": dependency.timeout_ms,
                    }
                    for service in ServiceDefinition.objects.prefetch_related(
                        "dependencies"
                    ).all()
                    for dependency in service.dependencies.all()
                ]
            }
        )
