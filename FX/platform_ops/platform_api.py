import hashlib
import json
from datetime import datetime, timezone
from django.conf import settings
from django.utils import timezone as django_timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trading.application.simulation import simulation_available
from apps.compliance.domain import KycState
from apps.compliance.models import ComplianceProfile
from platform_ops.health.services import HealthAuthority
from platform_ops.permissions import IsSreViewer


class PlatformConfigView(APIView):
    """
    GET /api/v1/platform/config
    Public platform configuration and runtime profile.
    """
    permission_classes = (AllowAny,)

    def get(self, request):
        config_data = {
            "schema_version": "1.0",
            "environment": getattr(settings, "DEPLOYMENT_ENV", "staging"),
            "product_mode": "SIMULATION_ONLY" if not getattr(settings, "REAL_TRADING_ENABLED", False) else "HYBRID",
            "simulation_enabled": simulation_available(),
            "live_trading_enabled": False,
            "real_money_enabled": False,
            "external_execution_enabled": False,
            "custody_enabled": False,
            "api_version": "v1",
            "supported_versions": ["v1"],
            "as_of": django_timezone.now().isoformat(),
        }

        # Compute deterministic ETag
        content_hash = hashlib.sha256(json.dumps(config_data, sort_keys=True).encode("utf-8")).hexdigest()
        etag = f'"{content_hash}"'

        if request.headers.get("If-None-Match") == etag:
            return Response(status=304)

        response = Response(config_data)
        response["ETag"] = etag
        response["Cache-Control"] = "private, no-store"
        response["Pragma"] = "no-cache"
        return response


class PlatformCapabilitiesView(APIView):
    """
    GET /api/v1/platform/capabilities
    Evaluates dynamic tenant capabilities, operational state, compliance and features.
    """
    permission_classes = (AllowAny,)

    def get(self, request):
        system_state = HealthAuthority.system_state()
        is_maintenance = system_state == "UNHEALTHY"
        is_degraded = system_state == "DEGRADED"

        # Safe defaults
        compliance_summary = {
            "trading_eligible": False,
            "policy_version": "2026.08.v1",
            "reason_codes": [],
            "requirements": [],
        }

        # Check authenticated user compliance if available
        if request.user.is_authenticated:
            profile = ComplianceProfile.objects.filter(user_id=request.user.pk).first()
            if profile and profile.kyc_state == KycState.APPROVED:
                compliance_summary["trading_eligible"] = True
            else:
                compliance_summary["reason_codes"].append("KYC_VERIFICATION_REQUIRED")

        # Hide internal provider details from non-operators
        is_operator = request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser)

        provider_health = None
        if is_operator:
            provider_health = {
                "execution_broker": "OPERATIONAL",
                "market_data_feed": "OPERATIONAL",
                "banking_rail": "OPERATIONAL"
            }

        capabilities_data = {
            "schema_version": "1.0",
            "environment": getattr(settings, "DEPLOYMENT_ENV", "staging"),
            "product_mode": "SIMULATION_ONLY",
            "simulation_enabled": simulation_available() and not is_maintenance,
            "live_trading_enabled": False,
            "real_money_enabled": False,
            "maintenance_mode": is_maintenance,
            "degraded_mode": is_degraded,
            "degraded_reasons": ["SYSTEM_STATE_DEGRADED"] if is_degraded else [],
            "supported_asset_classes": ["EQUITY", "CRYPTO"],
            "supported_order_types": ["MARKET", "LIMIT"],
            "supported_time_in_force": ["DAY", "GTC"],
            "market_data_intervals": ["1m", "5m", "15m", "1h", "1d"],
            "deposits": {
                "available": False,
                "reason_code": "FEATURE_DISABLED"
            },
            "withdrawals": {
                "available": False,
                "reason_code": "FEATURE_DISABLED"
            },
            "provider_health_visible": is_operator,
            "compliance": compliance_summary,
            "as_of": django_timezone.now().isoformat(),
        }

        if provider_health is not None:
            capabilities_data["provider_health"] = provider_health

        # Compute deterministic ETag
        content_hash = hashlib.sha256(json.dumps(capabilities_data, sort_keys=True).encode("utf-8")).hexdigest()
        etag = f'"{content_hash}"'

        if request.headers.get("If-None-Match") == etag:
            return Response(status=304)

        response = Response(capabilities_data)
        response["ETag"] = etag
        response["Cache-Control"] = "private, no-store"
        response["Pragma"] = "no-cache"
        return response
