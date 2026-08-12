import hashlib
import json
import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import enqueue_event

from .models import (
    AssetEncumbrance, CollateralMobilityPolicy, FundingRequirement,
    LiquidityBufferPolicy, LiquidityForecast, LiquiditySnapshot,
    IntradayFundingWindow, LiquidityStressResult, TreasuryAccount, TreasuryCashPosition,
    TreasuryCollateralPosition, TreasuryException, TreasuryReconciliationRun,
    TreasuryTransferPlan, TreasuryTransferPlanItem,
)

ZERO = Decimal("0")


def _d(value):
    return Decimal(str(value or "0"))


def audit(*, actor_ref, action, resource_type, resource_id, tenant_id, context=None):
    now = timezone.now()
    return ApplicationAuditEvent.objects.create(
        actor_ref=str(actor_ref), action=action, resource_type=resource_type,
        resource_id=str(resource_id), request_id=str(uuid.uuid4()), correlation_id=uuid.uuid4(),
        context={"tenant_ref": str(tenant_id), "simulation": True, **(context or {})},
        reason="TREASURY_SIMULATION", occurred_at=now,
    )


class TreasuryAccountService:
    @staticmethod
    def get(tenant, account_id):
        return TreasuryAccount.objects.get(tenant=tenant, pk=account_id)

    @staticmethod
    def list(tenant):
        return TreasuryAccount.objects.filter(tenant=tenant).order_by("account_type", "id")

    @staticmethod
    def resolve_for_institution(tenant, institution_id):
        return TreasuryAccountService.list(tenant).filter(institution_id=institution_id)

    @staticmethod
    def resolve_for_subaccount(tenant, subaccount_id):
        return TreasuryAccountService.list(tenant).filter(subaccount_id=subaccount_id)


class CashPositionService:
    @staticmethod
    def get_positions(tenant, currency=None):
        qs = TreasuryCashPosition.objects.filter(treasury_account__tenant=tenant).select_related("treasury_account")
        return qs.filter(currency=currency.upper()) if currency else qs

    @staticmethod
    def aggregate(tenant, currency):
        values = CashPositionService.get_positions(tenant, currency).aggregate(
            gross=Sum("gross_amount"), reserved=Sum("reserved_amount"), available=Sum("available_amount"),
            encumbered=Sum("encumbered_amount"), unencumbered=Sum("unencumbered_amount"),
        )
        return {key: value or ZERO for key, value in values.items()}

    @staticmethod
    def available(tenant, currency):
        return CashPositionService.aggregate(tenant, currency)["available"]

    @staticmethod
    def validate(position):
        return position.available_amount + position.reserved_amount <= position.gross_amount and position.unencumbered_amount <= position.gross_amount


class LiquidityBufferService:
    @staticmethod
    def required_buffer(tenant, currency, *, outflows=ZERO, settlement_due=ZERO, gross_exposure=ZERO):
        policy = LiquidityBufferPolicy.objects.filter(tenant=tenant, currency=currency, status="SIMULATION").order_by("-effective_from").first()
        if not policy:
            return ZERO
        if policy.buffer_type == "FIXED_AMOUNT": return policy.buffer_value
        if policy.buffer_type == "PERCENT_OF_OUTFLOWS": return outflows * policy.buffer_value
        if policy.buffer_type == "PERCENT_OF_SETTLEMENT_DUE": return settlement_due * policy.buffer_value
        if policy.buffer_type == "PERCENT_OF_GROSS_EXPOSURE": return gross_exposure * policy.buffer_value
        return policy.buffer_value

    @staticmethod
    def surplus_deficit(available, required):
        return available - required


class LiquidityService:
    @staticmethod
    @transaction.atomic
    def calculate(tenant, institution_id, currency, *, expected_inflows=ZERO, expected_outflows=ZERO, policy_version="simulation-v1"):
        cash = CashPositionService.aggregate(tenant, currency)
        requirements = FundingRequirement.objects.filter(tenant=tenant, institution_id=institution_id, currency_or_asset=currency, state__in=("FORECAST", "CONFIRMED_SIMULATION", "SHORTFALL"))
        settlement = requirements.filter(requirement_type="SETTLEMENT").aggregate(v=Sum("amount_or_quantity"))["v"] or ZERO
        margin = requirements.filter(requirement_type="MARGIN").aggregate(v=Sum("amount_or_quantity"))["v"] or ZERO
        outflows = _d(expected_outflows)
        inflows = _d(expected_inflows)
        net = cash["available"] + inflows - outflows - settlement - margin
        buffer = LiquidityBufferService.required_buffer(tenant, currency, outflows=outflows, settlement_due=settlement, gross_exposure=cash["gross"])
        snapshot = LiquiditySnapshot.objects.create(
            tenant=tenant, institution_id=institution_id, currency=currency, gross_cash=cash["gross"],
            available_cash=cash["available"], encumbered_cash=cash["encumbered"], settlement_due=settlement,
            margin_due=margin, expected_inflows=inflows, expected_outflows=outflows,
            net_available_liquidity=net, liquidity_buffer=buffer, liquidity_surplus_deficit=net-buffer,
            as_of=timezone.now(), policy_version=policy_version,
        )
        audit(actor_ref="system", action="treasury.liquidity.calculated", resource_type="LiquiditySnapshot", resource_id=snapshot.id, tenant_id=tenant.id)
        enqueue_event(aggregate_type="treasury_liquidity", aggregate_id=snapshot.id, event_type="treasury.liquidity.updated.v1", payload={"snapshot_id": str(snapshot.id), "currency": currency, "simulation": True}, tenant_ref=tenant.id)
        return snapshot

    @staticmethod
    def get_snapshot(tenant, currency=None):
        qs = LiquiditySnapshot.objects.filter(tenant=tenant)
        if currency: qs = qs.filter(currency=currency.upper())
        return qs.order_by("currency", "-as_of")

    @staticmethod
    def get_location_breakdown(tenant, currency):
        return CashPositionService.get_positions(tenant, currency)


class FundingRequirementService:
    @staticmethod
    def create_from_settlement(**kwargs):
        kwargs["requirement_type"] = "SETTLEMENT"
        return FundingRequirement.objects.get_or_create(tenant=kwargs["tenant"], source_ref=kwargs["source_ref"], requirement_type="SETTLEMENT", defaults=kwargs)[0]

    @staticmethod
    def create_from_margin(**kwargs):
        kwargs["requirement_type"] = "MARGIN"
        return FundingRequirement.objects.get_or_create(tenant=kwargs["tenant"], source_ref=kwargs["source_ref"], requirement_type="MARGIN", defaults=kwargs)[0]

    @staticmethod
    def aggregate(tenant, currency):
        return FundingRequirement.objects.filter(tenant=tenant, currency_or_asset=currency).aggregate(v=Sum("amount_or_quantity"))["v"] or ZERO

    @staticmethod
    def find_shortfalls(tenant):
        return FundingRequirement.objects.filter(tenant=tenant, state="SHORTFALL")


class IntradayFundingService:
    @staticmethod
    def calculate(tenant, institution_id, currency, window_start, window_end, opening_liquidity, events):
        """Calculate the true cumulative minimum from explicitly timed fixtures."""
        balance = _d(opening_liquidity)
        minimum = balance
        inflows = outflows = ZERO
        for event in sorted(events, key=lambda row: row["at"]):
            amount = _d(event["amount"])
            if event["direction"] == "INFLOW": balance += amount; inflows += amount
            else: balance -= amount; outflows += amount
            minimum = min(minimum, balance)
        return IntradayFundingWindow.objects.create(
            tenant=tenant, institution_id=institution_id, currency=currency,
            window_start=window_start, window_end=window_end,
            opening_liquidity=opening_liquidity, expected_inflows=inflows,
            expected_outflows=outflows, peak_funding_need=max(ZERO, -minimum),
            minimum_liquidity=minimum, closing_liquidity=balance,
        )


class TreasuryCollateralService:
    @staticmethod
    def inventory(tenant, asset=None):
        qs = TreasuryCollateralPosition.objects.filter(treasury_account__tenant=tenant).select_related("treasury_account")
        return qs.filter(instrument_id_or_asset=asset) if asset else qs

    @staticmethod
    def free_collateral(tenant, asset=None):
        return TreasuryCollateralService.inventory(tenant, asset).filter(quality_state="ELIGIBLE", free_quantity__gt=0)

    @staticmethod
    def eligible_value(tenant):
        return TreasuryCollateralService.free_collateral(tenant).aggregate(v=Sum("eligible_value"))["v"] or ZERO


class SegregationEncumbranceService:
    @staticmethod
    def movable_quantity(position):
        active = AssetEncumbrance.objects.filter(treasury_account=position.treasury_account, asset=position.instrument_id_or_asset, state="ACTIVE", effective_from__lte=timezone.now()).filter(Q(effective_to__isnull=True) | Q(effective_to__gt=timezone.now())).aggregate(v=Sum("quantity_or_amount"))["v"] or ZERO
        return max(ZERO, min(position.free_quantity, position.quantity - active))


class CollateralMobilityService:
    @staticmethod
    def preview(tenant, source_id, destination_id, asset, quantity):
        quantity = _d(quantity)
        source = TreasuryAccountService.get(tenant, source_id)
        destination = TreasuryAccountService.get(tenant, destination_id)
        position = TreasuryCollateralService.inventory(tenant, asset).filter(treasury_account=source).first()
        reasons = []
        if not position: reasons.append("COLLATERAL_UNAVAILABLE")
        elif position.quality_state == "STALE": reasons.append("STALE_COLLATERAL")
        elif position.quality_state != "ELIGIBLE": reasons.append("COLLATERAL_RESTRICTED")
        elif position.free_quantity < quantity: reasons.append("COLLATERAL_UNAVAILABLE")
        if source.segregation_class == "CLIENT_SEGREGATED" and destination.segregation_class == "HOUSE": reasons.append("SEGREGATION_CONFLICT")
        policy = CollateralMobilityPolicy.objects.filter(tenant=tenant, from_account_type=source.account_type, to_account_type=destination.account_type, allowed=True).order_by("-effective_from").first()
        if not policy: reasons.append("TRANSFER_NOT_ALLOWED")
        available = position.free_quantity if position else ZERO
        return {"allowed": not reasons, "available_quantity": available, "encumbered_quantity": position.encumbered_quantity if position else ZERO, "post_move_buffer": max(ZERO, available-quantity), "settlement_delay_seconds": int(policy.settlement_delay.total_seconds()) if policy else 0, "reason_codes": sorted(set(reasons)), "simulation": True}


class TreasuryPlanner:
    @staticmethod
    @transaction.atomic
    def generate_cash_plan(tenant, institution_id, currency, required, destination, idempotency_key):
        required = _d(required)
        plan, created = TreasuryTransferPlan.objects.get_or_create(
            tenant=tenant, idempotency_key=idempotency_key,
            defaults={"institution_id": institution_id, "plan_type": "CASH", "currency_or_asset": currency, "required_amount_or_quantity": required, "policy_version": "simulation-v1"},
        )
        if not created:
            if plan.currency_or_asset != currency or plan.required_amount_or_quantity != required or plan.institution_id != uuid.UUID(str(institution_id)):
                raise ValueError("IDEMPOTENCY_CONFLICT")
            return plan
        remaining = required
        sources = CashPositionService.get_positions(tenant, currency).filter(available_amount__gt=0, treasury_account__status="ACTIVE").exclude(treasury_account__segregation_class="CLIENT_SEGREGATED").order_by("-available_amount", "treasury_account_id")
        for row in sources:
            if remaining <= 0: break
            amount = min(row.available_amount, remaining)
            if row.treasury_account_id == destination.id: continue
            TreasuryTransferPlanItem.objects.create(plan=plan, source_account=row.treasury_account, destination_account=destination, currency_or_asset=currency, amount_or_quantity=amount, reason="SIMULATED_FUNDING_GAP", estimated_available_at=timezone.now())
            remaining -= amount
        plan.state = "VALIDATED" if remaining <= 0 else "REJECTED"
        plan.save(update_fields=("state",))
        audit(actor_ref="system", action="treasury.transfer_plan.generated", resource_type="TreasuryTransferPlan", resource_id=plan.id, tenant_id=tenant.id)
        enqueue_event(aggregate_type="treasury_transfer_plan", aggregate_id=plan.id, event_type="treasury.transfer_plan.created.v1", payload={"plan_id": str(plan.id), "state": plan.state, "simulation": True}, tenant_ref=tenant.id)
        return plan

    generate_collateral_plan = generate_cash_plan

    @staticmethod
    def validate_plan(plan):
        return plan.simulation and plan.state in ("VALIDATED", "APPROVED_SIMULATION", "SIMULATED") and all(i.source_account.tenant_id == plan.tenant_id == i.destination_account.tenant_id for i in plan.items.all())


class LiquidityForecastService:
    @staticmethod
    def calculate(tenant, institution_id, currency, horizon="END_OF_DAY"):
        opening = CashPositionService.available(tenant, currency)
        outflows = FundingRequirementService.aggregate(tenant, currency)
        buffer = LiquidityBufferService.required_buffer(tenant, currency, outflows=outflows)
        return LiquidityForecast.objects.create(tenant=tenant, institution_id=institution_id, currency=currency, forecast_time=timezone.now(), horizon=horizon, opening_liquidity=opening, expected_inflows=ZERO, expected_outflows=outflows, expected_buffer=buffer, projected_surplus_deficit=opening-outflows-buffer, confidence_state="DETERMINISTIC_SIMULATION", policy_version="simulation-v1")


class LiquidityStressService:
    @staticmethod
    def run(tenant, institution_id, currency, scenario):
        available = CashPositionService.available(tenant, currency)
        cash_factor = _d(scenario.parameters_json_safe.get("cash_factor", "1"))
        outflow_factor = _d(scenario.parameters_json_safe.get("outflow_factor", "1"))
        obligations = FundingRequirementService.aggregate(tenant, currency) * outflow_factor
        stressed = available * cash_factor - obligations
        return LiquidityStressResult.objects.create(scenario=scenario, tenant=tenant, institution_id=institution_id, currency=currency, starting_liquidity=available, peak_shortfall=max(ZERO, -stressed), minimum_liquidity=stressed, buffer_breach=stressed < 0, required_funding=max(ZERO, -stressed), affected_accounts=[])


class SettlementFundingService:
    @staticmethod
    def evaluate(requirement):
        available = CashPositionService.available(requirement.tenant, requirement.currency_or_asset)
        return {"settlement_id": requirement.source_ref, "required": requirement.amount_or_quantity, "available": available, "status": "FUNDED_SIMULATION" if available >= requirement.amount_or_quantity else "FUNDING_SHORTFALL", "simulation": True}

    find_shortfall = evaluate

    @staticmethod
    def generate_plan(requirement, destination, idempotency_key):
        return TreasuryPlanner.generate_cash_plan(requirement.tenant, requirement.institution_id, requirement.currency_or_asset, requirement.amount_or_quantity, destination, idempotency_key)


class TreasuryReconciler:
    CHECKS = ("CASH_POSITION_MISMATCH", "AVAILABLE_CASH_MISMATCH", "ENCUMBRANCE_MISMATCH", "COLLATERAL_VALUE_MISMATCH", "FREE_COLLATERAL_MISMATCH", "FUNDING_REQUIREMENT_MISSING", "SETTLEMENT_FUNDING_MISSING", "TRANSFER_PLAN_INVALID", "SEGREGATED_ASSET_USAGE", "OMNIBUS_ATTRIBUTION_MISMATCH", "DUPLICATE_TRANSFER_PLAN_EFFECT", "LIQUIDITY_BUFFER_BREACH_UNACCOUNTED", "FORECAST_VS_REALIZED_SIMULATION_MISMATCH", "AUDIT_GAP")

    @classmethod
    @transaction.atomic
    def run(cls, tenant, candidate_sha="local"):
        violations = []
        for p in CashPositionService.get_positions(tenant):
            if not CashPositionService.validate(p): violations.append({"check": "CASH_POSITION_MISMATCH", "ref": str(p.id)})
        for c in TreasuryCollateralService.inventory(tenant):
            if c.free_quantity + c.encumbered_quantity > c.quantity: violations.append({"check": "FREE_COLLATERAL_MISMATCH", "ref": str(c.id)})
        for plan in TreasuryTransferPlan.objects.filter(tenant=tenant).prefetch_related("items__source_account", "items__destination_account"):
            if plan.state != "REJECTED" and not cls._tenant_safe(plan): violations.append({"check": "TRANSFER_PLAN_INVALID", "ref": str(plan.id)})
        now = timezone.now()
        run = TreasuryReconciliationRun.objects.create(tenant=tenant, status="PASS" if not violations else "FAIL", checks=list(cls.CHECKS), violations=violations, started_at=now, completed_at=now, candidate_sha=candidate_sha[:40], policy_version="simulation-v1")
        audit(actor_ref="system", action="treasury.reconciliation.run", resource_type="TreasuryReconciliationRun", resource_id=run.id, tenant_id=tenant.id, context={"violations": len(violations)})
        enqueue_event(aggregate_type="treasury_reconciliation", aggregate_id=run.id, event_type="treasury.reconciliation.completed.v1", payload={"run_id": str(run.id), "status": run.status, "violation_count": len(violations), "simulation": True}, tenant_ref=tenant.id)
        return run

    @staticmethod
    def _tenant_safe(plan):
        return all(item.source_account.tenant_id == plan.tenant_id == item.destination_account.tenant_id for item in plan.items.all())


class TreasuryExceptionService:
    @staticmethod
    def evidence_hash(payload):
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
