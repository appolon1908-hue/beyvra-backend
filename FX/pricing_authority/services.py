from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import AccountEntitlementOverride, AccountPlanAssignment, FeeRule, FeeWaiver, PlanEntitlement, PricingRoundingPolicy


@dataclass(frozen=True)
class EntitlementDecision:
    entitlement_code: str
    state: str
    limit: Decimal | None
    effective_policy_version: str


def resolve_entitlement(account, code, at=None):
    at = at or timezone.now()
    if code in {"REAL_TRADING", "REAL_MONEY", "WITHDRAWALS", "DEPOSITS", "TRANSFERS"}:
        return EntitlementDecision(code, "DENY", None, "global-safety-v1")
    override = AccountEntitlementOverride.objects.filter(account=account, entitlement__code=code, status="ACTIVE", effective_from__lte=at).filter(Q(effective_to__isnull=True)|Q(effective_to__gt=at)).order_by("-effective_from").first()
    if override:
        state = "DENY" if override.override_type == "DISABLE" else ("LIMITED" if override.override_type == "LIMIT_OVERRIDE" else "ALLOW")
        return EntitlementDecision(code, state, override.value, f"override-{override.pk}")
    assignment = AccountPlanAssignment.objects.filter(account=account, status="ACTIVE", effective_from__lte=at).filter(Q(effective_to__isnull=True)|Q(effective_to__gt=at)).select_related("plan_version").first()
    if not assignment:
        return EntitlementDecision(code, "DENY", None, "default-deny-v1")
    mapping = PlanEntitlement.objects.filter(plan_version=assignment.plan_version, entitlement__code=code).first()
    if not mapping or not mapping.enabled:
        return EntitlementDecision(code, "DENY", None, f"plan-{assignment.plan_version_id}")
    return EntitlementDecision(code, "LIMITED" if mapping.limit_value is not None else "ALLOW", mapping.limit_value, f"plan-{assignment.plan_version_id}")


def market_data_access(account, provider_capability, at=None):
    if provider_capability == "REALTIME" and resolve_entitlement(account, "MARKET_DATA_REALTIME", at).state != "DENY":
        return "REALTIME"
    if resolve_entitlement(account, "MARKET_DATA_DELAYED", at).state != "DENY":
        return "DELAYED"
    return "NOT_AVAILABLE"


def calculate_fee(*, account, fee_type, notional, quantity, asset_class="", at=None):
    at = at or timezone.now()
    if not isinstance(notional, Decimal) or not isinstance(quantity, Decimal):
        raise ValueError("Money and quantity must use Decimal")
    if notional < 0 or quantity < 0:
        raise ValueError("Negative context values are invalid")
    waiver = FeeWaiver.objects.filter(account=account, fee_type=fee_type, effective_from__lte=at).filter(Q(effective_to__isnull=True)|Q(effective_to__gt=at)).exists()
    if waiver:
        return {"amount": Decimal("0"), "currency": None, "rule_version": None, "breakdown": {"waiver": True}, "estimated": True}
    rule = FeeRule.objects.filter(schedule__fee_type=fee_type, schedule__status="ACTIVE", effective_from__lte=at).filter(Q(effective_to__isnull=True)|Q(effective_to__gt=at)).filter(Q(asset_class="")|Q(asset_class=asset_class)).select_related("schedule").order_by("schedule__priority", "-rule_version").first()
    if not rule:
        raise ValueError("FEE_POLICY_UNAVAILABLE")
    bases = {"FLAT": Decimal("1"), "PERCENT": notional / Decimal("100"), "BASIS_POINTS": notional / Decimal("10000"), "PER_SHARE": quantity, "PER_CONTRACT": quantity, "PER_UNIT": quantity}
    if rule.rate_type not in bases:
        raise ValueError("TIER_SOURCE_UNAVAILABLE")
    amount = bases[rule.rate_type] * rule.rate_value
    if rule.min_fee is not None: amount = max(amount, rule.min_fee)
    if rule.max_fee is not None: amount = min(amount, rule.max_fee)
    policy = PricingRoundingPolicy.objects.filter(currency=rule.currency, effective_from__lte=at).filter(Q(effective_to__isnull=True)|Q(effective_to__gt=at)).order_by("-effective_from").first()
    places = policy.decimal_places if policy else 2
    amount = amount.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if amount < 0 and not rule.is_rebate:
        raise ValueError("UNEXPECTED_NEGATIVE_FEE")
    return {"amount": amount, "currency": rule.currency, "rule_version": rule.rule_version, "breakdown": {"customer_fee": amount}, "estimated": True}
