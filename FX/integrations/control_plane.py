"""Read-only composition for the Beyvra account and tenant control plane.

This module owns no state. It composes decisions from the canonical identity,
tenant, pricing, compliance, provider-governance, and reference-data owners.
"""

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.compliance.models import ComplianceProfile
from apps.compliance.services import (
    POLICY_VERSION as COMPLIANCE_POLICY_VERSION,
    effective_profile_states,
    get_deposit_eligibility,
    get_trading_eligibility,
    get_transfer_eligibility,
    get_withdrawal_eligibility,
)
from pricing_authority.services import (
    current_plan_assignment,
    entitlement_decisions,
    market_data_access,
)
from provider_governance.models import ProviderDefinition
from reference_data.models import Instrument, ProviderSymbolMapping

from .models import OrganizationMembership
from .permissions import tenant_context_for_request


CONTRACT_VERSION = "2026-08-27.v1"


def _enum_value(value):
    return getattr(value, "value", value)


def _compliance_context(user, organization):
    profile = ComplianceProfile.objects.filter(
        user=user,
        organization=organization,
    ).first()
    if profile is None:
        capabilities = {
            capability: {
                "result": "DENIED",
                "reason_codes": ["COMPLIANCE_PROFILE_REQUIRED"],
                "policy_version": COMPLIANCE_POLICY_VERSION,
            }
            for capability in ("TRADING", "DEPOSIT", "WITHDRAWAL", "TRANSFER")
        }
        return {
            "status": "REQUIRED",
            "profile_version": None,
            "states": None,
            "open_requirements": [],
            "capabilities": capabilities,
        }

    now = timezone.now()
    states = effective_profile_states(profile, now)
    evaluators = {
        "TRADING": get_trading_eligibility,
        "DEPOSIT": get_deposit_eligibility,
        "WITHDRAWAL": get_withdrawal_eligibility,
        "TRANSFER": get_transfer_eligibility,
    }
    capabilities = {}
    for capability, evaluator in evaluators.items():
        decision = evaluator(profile, persist=False, context_ref="control-plane")
        capabilities[capability] = {
            "result": _enum_value(decision.result),
            "reason_codes": list(decision.reason_codes),
            "policy_version": decision.policy_version,
            "evaluated_at": decision.evaluated_at,
        }
    requirements = profile.requirements.filter(required=True).exclude(
        status__in=("COMPLETED", "WAIVED")
    ).order_by("type", "requirement_id")
    return {
        "status": "READY" if capabilities["TRADING"]["result"] == "ALLOWED" else "RESTRICTED",
        "profile_version": profile.version,
        "states": {key: _enum_value(value) for key, value in states.items()},
        "open_requirements": [{
            "requirement_id": str(item.pk),
            "type": item.type,
            "status": item.status,
            "deadline": item.deadline,
        } for item in requirements],
        "capabilities": capabilities,
    }


def _market_data_context(user, tenant_id):
    now = timezone.now()
    active_mapping_filter = Q(effective_from__lte=now) & (
        Q(effective_to__isnull=True) | Q(effective_to__gt=now)
    )
    mappings = ProviderSymbolMapping.objects.filter(
        active_mapping_filter,
        product="MARKET_DATA",
        instrument__status=Instrument.Status.ACTIVE,
    )
    active_instruments = mappings.values("instrument_id").distinct().count()
    governed_providers = ProviderDefinition.objects.filter(
        provider_type="MARKET_DATA",
        enabled=True,
        license_verified=True,
        security_approved=True,
        compliance_approved=True,
    ).count()
    return {
        "access": market_data_access(user, "REALTIME", tenant_ref=tenant_id),
        "instrument_authority": "reference_data.Instrument",
        "mapping_authority": "reference_data.ProviderSymbolMapping",
        "normalization_authority": "trade.market_authority",
        "provider_activation_authority": "provider_governance",
        "active_instrument_count": active_instruments,
        "governed_provider_count": governed_providers,
        "freshness_policy": "per-response-fail-closed",
        "demo_fixture_enabled": bool(getattr(settings, "DEMO_MARKET_FIXTURE_ENABLED", False)),
    }


def build_control_plane_context(request):
    selected = tenant_context_for_request(request)
    organization = selected.organization
    tenant_id = str(organization.id)
    now = timezone.now()
    assignment, _ambiguous = current_plan_assignment(
        request.user,
        tenant_ref=tenant_id,
        at=now,
    )
    decisions = entitlement_decisions(request.user, tenant_id, at=now)
    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
    ).select_related("organization").order_by("organization__name", "organization_id")

    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": now,
        "account": {
            "account_id": str(request.user.pk),
            "email": request.user.email,
            "active": request.user.is_active,
            "identity_authority": "KEYCLOAK" if getattr(settings, "KEYCLOAK_IDENTITY_ENABLED", False) else "LOCAL_COMPATIBILITY",
            "identity_bound": bool(getattr(request.user, "identity_subject", "")),
        },
        "tenant": {
            "tenant_id": tenant_id,
            "name": organization.name,
            "active": organization.is_active,
            "role": selected.role,
            "selection_source": selected.source,
        },
        "memberships": [{
            "tenant_id": str(item.organization_id),
            "name": item.organization.name,
            "role": item.role,
        } for item in memberships],
        "plan": None if assignment is None else {
            "code": assignment.plan_version.plan.code,
            "name": assignment.plan_version.plan.name,
            "version": assignment.plan_version.version,
            "policy_ref": f"plan-{assignment.plan_version_id}",
        },
        "entitlements": [{
            "code": item.entitlement_code,
            "state": item.state,
            "limit": str(item.limit) if item.limit is not None else None,
            "unit": item.limit_unit,
            "source": item.source,
            "policy_version": item.effective_policy_version,
        } for item in decisions],
        "compliance": _compliance_context(request.user, organization),
        "market_data": _market_data_context(request.user, tenant_id),
        "execution": {
            "simulation_enabled": bool(getattr(settings, "SIMULATED_TRADING_ENABLED", False)),
            "paper_trading_allowed": bool(getattr(settings, "PAPER_TRADING_ALLOWED", False)),
            "real_trading_enabled": bool(getattr(settings, "REAL_TRADING_ENABLED", False)),
            "external_execution_enabled": bool(getattr(settings, "EXTERNAL_EXECUTION_ENABLED", False)),
            "real_money_enabled": bool(getattr(settings, "REAL_MONEY_ENABLED", False)),
        },
        "authorities": {
            "identity": "Keycloak",
            "tenant": "integrations.OrganizationMembership",
            "entitlement": "pricing_authority",
            "compliance": "apps.compliance",
            "market_reference": "reference_data",
            "market_normalization": "trade.market_authority",
            "provider_activation": "provider_governance",
            "composition_only": "integrations.control_plane",
        },
    }
