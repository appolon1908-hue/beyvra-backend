import os
import re

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.foundation.read_only import database_read_only_state
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


def _safety_state():
    deployment_read_only = _env_true("DEPLOYMENT_READ_ONLY")
    return {
        "simulation_enabled": bool(settings.SIMULATED_TRADING_ENABLED),
        "live_trading_enabled": bool(
            getattr(settings, "LIVE_TRADING_ENABLED", False)
        ),
        "real_trading_enabled": bool(
            getattr(settings, "REAL_TRADING_ENABLED", False)
        ),
        "real_money_enabled": bool(
            getattr(settings, "REAL_MONEY_ENABLED", False)
        ),
        "real_deposits_enabled": bool(
            getattr(settings, "REAL_DEPOSITS_ENABLED", False)
        ),
        "real_withdrawals_enabled": bool(
            getattr(settings, "REAL_WITHDRAWALS_ENABLED", False)
        ),
        "real_internal_transfers_enabled": bool(
            getattr(settings, "REAL_INTERNAL_TRANSFERS_ENABLED", False)
        ),
        "external_execution_enabled": bool(
            getattr(settings, "EXTERNAL_EXECUTION_ENABLED", False)
        ),
        "live_broker_routing_enabled": bool(
            getattr(settings, "LIVE_BROKER_ROUTING_ENABLED", False)
        ),
        "fix_live_session_enabled": bool(
            getattr(settings, "FIX_LIVE_SESSION_ENABLED", False)
        ),
        "payments_enabled": bool(
            getattr(settings, "PAYMENTS_ENABLED", False)
        ),
        "transactional_email_enabled": bool(
            getattr(settings, "TRANSACTIONAL_EMAIL_ENABLED", False)
        ),
        "welcome_email_enabled": bool(
            getattr(settings, "WELCOME_EMAIL_ENABLED", False)
        ),
        "legacy_realtime_fallback_enabled": bool(
            getattr(settings, "REALTIME_V2_V1_FALLBACK_ENABLED", False)
        ),
        "deployment_read_only": deployment_read_only,
    }


def live(_request):
    return JsonResponse({"status": "live"})


def ready(_request):
    pg = check_postgres()
    redis = check_redis()
    deployment_read_only = _env_true("DEPLOYMENT_READ_ONLY")
    database_read_only = (
        database_read_only_state() if deployment_read_only else True
    )
    nats_required = (
        bool(settings.NATS_JETSTREAM_ENABLED) and not deployment_read_only
    )
    nats = not nats_required or bool(cache.get("health:outbox-worker"))
    ok = pg[0] and redis[0] and nats and database_read_only
    return JsonResponse(
        {
            "status": "ready" if ok else "not_ready",
            "checks": {
                "postgresql": pg[0],
                "postgresql_read_only": (
                    database_read_only if deployment_read_only else "not_required"
                ),
                "redis": redis[0],
                "nats": (
                    "not_required_read_only"
                    if deployment_read_only
                    else (
                        "disabled"
                        if not settings.NATS_JETSTREAM_ENABLED
                        else ("ready" if nats else "worker_unavailable")
                    )
                ),
            },
        },
        status=200 if ok else 503,
    )


class SystemStatusView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        state = HealthAuthority.system_state()
        if not settings.SIMULATED_TRADING_ENABLED:
            simulation_state = "DISABLED"
        else:
            simulation_state = (
                "AVAILABLE"
                if state in {"HEALTHY", "DEGRADED"}
                else "UNAVAILABLE"
            )
        return Response(
            {
                "system_state": state,
                "market_data_state": (
                    "UNAVAILABLE" if state == "UNHEALTHY" else "DEGRADED"
                ),
                "trading_simulation_state": simulation_state,
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
        safety = _safety_state()
        return Response(
            {
                "simulation": safety["simulation_enabled"],
                "market_data": True,
                "realtime": bool(settings.REALTIME_V2_ENABLED),
                "reports": True,
                "real_trading": safety["real_trading_enabled"],
                "real_money": safety["real_money_enabled"],
                "payments": safety["payments_enabled"],
                "transactional_email": safety[
                    "transactional_email_enabled"
                ],
                "external_execution": safety[
                    "external_execution_enabled"
                ],
                "deployment_read_only": safety["deployment_read_only"],
            }
        )


class ReleaseIdentityView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        source_sha = str(getattr(settings, "RELEASE_SHA", "")).strip()
        image_digest = os.getenv("BEYVRA_IMAGE_DIGEST", "").strip()
        safety = _safety_state()
        database_read_only = database_read_only_state()
        effect_flags_disabled = not any(
            value
            for key, value in safety.items()
            if key not in {"deployment_read_only"}
        )
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
            "deployment_read_only": safety["deployment_read_only"],
            "database_read_only_enforced": database_read_only,
            "effect_flags_disabled": effect_flags_disabled,
            "read_only_certified": bool(
                safety["deployment_read_only"]
                and database_read_only
                and effect_flags_disabled
            ),
            "immutable_identity_verified": bool(
                _SOURCE_SHA.fullmatch(source_sha)
                and _IMAGE_DIGEST.fullmatch(image_digest)
            ),
            "safety": safety,
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
