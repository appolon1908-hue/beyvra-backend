import hashlib
import json
import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.compliance.domain import RequirementType
from apps.compliance.models import ComplianceProfile
from apps.compliance.services import POLICY_VERSION, get_trading_eligibility
from apps.trading.application.simulation import simulation_available
from integrations.models import OrganizationMembership
from platform_ops.health.api import _safety_state
from platform_ops.health.services import HealthAuthority
from platform_ops.permissions import SRE_ROLES


def _etag(payload):
    stable = {key: value for key, value in payload.items() if key != "as_of"}
    digest = hashlib.sha256(
        json.dumps(
            stable,
            sort_keys=True,
            cls=DjangoJSONEncoder,
        ).encode("utf-8")
    ).hexdigest()
    return f'"{digest}"'


def _cached_response(payload, request):
    etag = _etag(payload)
    if request.headers.get("If-None-Match") == etag:
        response = Response(status=304)
    else:
        response = Response(payload)
    response["ETag"] = etag
    response["Cache-Control"] = "private, no-store"
    response["Pragma"] = "no-cache"
    return response


def _product_mode(safety):
    return (
        "HYBRID"
        if (
            safety["live_trading_enabled"]
            or safety["real_trading_enabled"]
            or safety["external_execution_enabled"]
        )
        else "SIMULATION_ONLY"
    )


def _provider_health_visible(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(
        user.is_superuser
        or OrganizationMembership.objects.filter(
            user=user,
            role__in=SRE_ROLES,
            is_active=True,
            organization__is_active=True,
        ).exists()
    )


def _compliance_summary(request):
    user = request.user
    summary = {
        "trading_eligible": False,
        "policy_version": POLICY_VERSION,
        "reason_codes": [],
        "requirements": [],
    }
    if not getattr(user, "is_authenticated", False):
        return summary
    organization = _resolve_compliance_organization(request)
    if organization is None:
        summary["reason_codes"] = ["KYC_REQUIRED"]
        summary["requirements"] = [RequirementType.IDENTITY_VERIFICATION.value]
        return summary
    profile = ComplianceProfile.objects.filter(
        user=user,
        organization=organization,
    ).first()
    if profile is None:
        summary["reason_codes"] = ["KYC_REQUIRED"]
        summary["requirements"] = [RequirementType.IDENTITY_VERIFICATION.value]
        return summary
    decision = get_trading_eligibility(profile, persist=False)
    summary["trading_eligible"] = decision.result == "ALLOWED"
    summary["policy_version"] = decision.policy_version
    summary["reason_codes"] = list(decision.reason_codes)
    summary["requirements"] = list(
        profile.requirements.filter(required=True)
        .exclude(status="COMPLETED")
        .values_list("type", flat=True)
    )
    return summary


def _resolve_compliance_organization(request):
    if not getattr(request.user, "is_authenticated", False):
        return None
    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
    ).select_related("organization").order_by("organization_id")
    organization_id = request.headers.get("X-Organization-ID")
    if organization_id:
        try:
            normalized_organization_id = uuid.UUID(str(organization_id))
        except (ValueError, TypeError, AttributeError):
            raise exceptions.PermissionDenied("invalid organization context")
        membership = memberships.filter(
            organization_id=normalized_organization_id
        ).first()
        if membership is None:
            raise exceptions.PermissionDenied(
                "organization context is not authorized"
            )
        return membership.organization
    available = list(memberships[:2])
    if len(available) == 1:
        return available[0].organization
    return None


class PlatformConfigView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        safety = _safety_state()
        payload = {
            "schema_version": "1.0",
            "environment": getattr(settings, "DEPLOYMENT_ENV", "staging"),
            "product_mode": _product_mode(safety),
            "simulation_enabled": simulation_available(),
            "live_trading_enabled": safety["live_trading_enabled"],
            "real_money_enabled": safety["real_money_enabled"],
            "external_execution_enabled": safety["external_execution_enabled"],
            "custody_enabled": bool(
                getattr(settings, "CUSTODY_ENABLED", False)
            ),
            "api_version": "v1",
            "supported_versions": ["v1"],
            "as_of": timezone.now().isoformat(),
        }
        return _cached_response(payload, request)


class PlatformCapabilitiesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        safety = _safety_state()
        system_state = HealthAuthority.system_state()
        provider_health_visible = _provider_health_visible(request.user)
        payload = {
            "schema_version": "1.0",
            "environment": getattr(settings, "DEPLOYMENT_ENV", "staging"),
            "product_mode": _product_mode(safety),
            "simulation_enabled": simulation_available()
            and system_state != "UNHEALTHY",
            "live_trading_enabled": safety["live_trading_enabled"],
            "real_money_enabled": safety["real_money_enabled"],
            "maintenance_mode": system_state == "UNHEALTHY",
            "degraded_mode": system_state == "DEGRADED",
            "degraded_reasons": (
                ["SYSTEM_STATE_DEGRADED"]
                if system_state == "DEGRADED"
                else []
            ),
            "supported_asset_classes": ["EQUITY", "CRYPTO"],
            "supported_order_types": ["MARKET", "LIMIT"],
            "supported_time_in_force": ["DAY", "GTC"],
            "market_data_intervals": ["1m", "5m", "15m", "1h", "1d"],
            "deposits": {
                "available": False,
                "reason_code": "FEATURE_DISABLED",
            },
            "withdrawals": {
                "available": False,
                "reason_code": "FEATURE_DISABLED",
            },
            "provider_health_visible": provider_health_visible,
            "compliance": _compliance_summary(request),
            "as_of": timezone.now().isoformat(),
        }
        if provider_health_visible:
            payload["provider_health"] = {
                "system_state": system_state,
                "services": HealthAuthority.latest(),
            }
        return _cached_response(payload, request)
