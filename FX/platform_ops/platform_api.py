import hashlib
import json
from django.conf import settings
from django.utils import timezone as django_timezone
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.compliance.domain import EligibilityResult
from apps.compliance.models import ComplianceProfile
from apps.compliance.services import get_trading_eligibility
from apps.trading.application.simulation import simulation_available
from integrations.permissions import organization_for_request
from platform_ops.health.services import HealthAuthority


def _etag(payload):
    content_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f'"{content_hash}"'


def _reason_requirements(reason_codes):
    requirements = []
    if any(code.startswith("KYC_") for code in reason_codes):
        requirements.append("IDENTITY_VERIFICATION")
    if any(code.startswith("AML_") for code in reason_codes):
        requirements.append("MANUAL_REVIEW")
    if any(code.startswith("SANCTIONS_") for code in reason_codes):
        requirements.append("MANUAL_REVIEW")
    if "JURISDICTION_RESTRICTED" in reason_codes:
        requirements.append("ADDRESS_VERIFICATION")
    return requirements


def _compliance_summary_for_request(request):
    summary = {
        "trading_eligible": False,
        "policy_version": "2026.08.v1",
        "reason_codes": [],
        "requirements": [],
    }
    if not request.user.is_authenticated:
        return summary
    try:
        organization = organization_for_request(request)
    except exceptions.APIException as exc:
        detail = exc.detail
        if isinstance(detail, dict) and detail.get("code"):
            summary["reason_codes"] = [str(detail["code"])]
        else:
            summary["reason_codes"] = ["ORGANIZATION_CONTEXT_REQUIRED"]
        return summary

    profile = ComplianceProfile.objects.filter(user_id=request.user.pk, organization=organization).first()
    if not profile:
        summary["reason_codes"] = ["KYC_REQUIRED"]
        summary["requirements"] = ["IDENTITY_VERIFICATION"]
        return summary

    decision = get_trading_eligibility(profile, persist=False)
    summary["trading_eligible"] = decision.result == EligibilityResult.ALLOWED
    summary["policy_version"] = decision.policy_version
    summary["reason_codes"] = list(decision.reason_codes)
    summary["requirements"] = _reason_requirements(summary["reason_codes"])
    return summary


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
        }
        etag = _etag(config_data)

        if request.headers.get("If-None-Match") == etag:
            return Response(status=304)

        response = Response({
            **config_data,
            "as_of": django_timezone.now().isoformat(),
        })
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

        compliance_summary = _compliance_summary_for_request(request)

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
        }

        if provider_health is not None:
            capabilities_data["provider_health"] = provider_health

        etag = _etag(capabilities_data)

        if request.headers.get("If-None-Match") == etag:
            return Response(status=304)

        response = Response({
            **capabilities_data,
            "as_of": django_timezone.now().isoformat(),
        })
        response["ETag"] = etag
        response["Cache-Control"] = "private, no-store"
        response["Pragma"] = "no-cache"
        return response
