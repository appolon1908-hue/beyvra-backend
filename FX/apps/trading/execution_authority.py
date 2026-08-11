import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import enqueue_event
from apps.trading.models import CanonicalExecution, ExecutionProviderRecord, ExecutionQualityReport, ExecutionRoutingDecision, ExecutionVenue, TradingOrder, UnknownExecutionOutcome
from apps.trading.execution_control.router import SmartOrderRouter, digest

POLICY_VERSION = "best-execution-sim-v1"
MEASUREMENT_VERSION = "execution-quality-v1"


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def assert_safe_mode(mode):
    mode = str(mode or "SIMULATION").upper()
    if settings.REAL_TRADING_ENABLED or settings.EXTERNAL_EXECUTION_ENABLED:
        raise ValueError("LIVE_EXECUTION_DISABLED")
    if mode == "LIVE" or settings.LIVE_BROKER_ROUTING_ENABLED or settings.FIX_LIVE_SESSION_ENABLED:
        raise ValueError("LIVE_EXECUTION_DISABLED")
    if mode == "PAPER" and not settings.PAPER_TRADING_ALLOWED:
        raise ValueError("PAPER_TRADING_DISABLED")
    if mode == "SIMULATION" and not settings.SIMULATION_ALLOWED:
        raise ValueError("SIMULATION_DISABLED")
    return mode


def seed_safe_authorities():
    provider, _ = ExecutionProviderRecord.objects.get_or_create(
        provider_id="simulation", defaults={"display_name": "Beyvra Simulation", "mode": "SIMULATION", "enabled": True,
        "health": "HEALTHY", "supported_asset_classes": ["CRYPTO", "EQUITY", "ETF"],
        "supported_order_types": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"], "supported_venues": ["BEYVRA-SIM"],
        "capabilities": {"submit": True, "cancel": True, "replace": True, "partial_fills": True, "network": False}}
    )
    ExecutionVenue.objects.get_or_create(venue_id="BEYVRA-SIM", defaults={"display_name": "Beyvra Simulation Venue", "active": True,
        "asset_classes": ["CRYPTO", "EQUITY", "ETF"], "order_types": ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
        "metadata": {"simulation": True, "external": False}})
    return provider


def preview_route(user, data, *, persist=False, order=None):
    mode = assert_safe_mode(data.get("mode", "SIMULATION"))
    try:
        instrument = str(data.get("instrument") or data.get("instrument_id") or "").upper()
        order_type = str(data.get("order_type") or "MARKET").upper()
        side = str(data.get("side") or "").upper()
        quantity = Decimal(str(data.get("quantity")))
        reference_price = Decimal(str(data.get("reference_price") or settings.SIMULATED_EXECUTION_PRICES.get(instrument)))
    except (InvalidOperation, TypeError):
        raise ValueError("VALIDATION_ERROR")
    if not instrument or side not in {"BUY", "SELL"} or quantity <= 0 or reference_price <= 0:
        raise ValueError("VALIDATION_ERROR")
    if data.get("market_data_stale") is True: raise ValueError("MARKET_DATA_STALE")
    snapshot={"instrument":instrument,"reference_price":str(reference_price),"source":data.get("market_source","deterministic_fixture")}
    request={"instrument_id":instrument,"side":side,"order_type":order_type,"quantity":str(quantity),"reference_price":str(reference_price),"mode":mode,
        "asset_class":str(data.get("asset_class") or "CRYPTO").upper(),"time_in_force":str(data.get("time_in_force") or "DAY").upper(),
        "limit_price":str(data["limit_price"]) if data.get("limit_price") is not None else None,"market_snapshot_hash":digest(snapshot),
        "pricing_snapshot_hash":digest({"fees":data.get("fees","fixture-policy")}),"risk_snapshot_hash":str(data.get("risk_snapshot_hash") or digest({"risk":"prechecked"})),
        "correlation_id":str(data.get("correlation_id") or uuid.uuid4())}
    result=SmartOrderRouter().route(user,request,order=order,persist=persist)
    result.update({"decision":"SELECTED" if result["routable"] else "DENIED","selected_provider_id":result["selected_route_summary"]["provider_id"] if result["routable"] else None,
        "selected_venue_id":result["selected_route_summary"]["venue_id"] if result["routable"] else None,"market_snapshot_hash":request["market_snapshot_hash"],
        "request_hash":digest(request),"live":False,"outbound_live_execution_requests":0,"real_financial_effects":0})
    return result


@transaction.atomic
def record_quality(order):
    decision = order.routing_decisions.order_by("-created_at").first()
    if not decision or not order.average_fill_price or not order.filled_quantity:
        raise ValueError("EXECUTION_QUALITY_NOT_AVAILABLE")
    reference, execution = decision.reference_price, order.average_fill_price
    signed = (execution - reference) if order.side == "BUY" else (reference - execution)
    slippage_bps = signed / reference * Decimal("10000")
    improvement = -signed
    fees=sum((x.fee for x in order.simulated_trades.all()), Decimal("0")); fill_rate=order.filled_quantity/order.quantity if order.quantity else Decimal("0")
    report, _ = ExecutionQualityReport.objects.update_or_create(order=order, defaults={"routing_decision": decision,
        "reference_price": reference, "execution_price": execution, "filled_quantity": order.filled_quantity,
        "slippage_bps": slippage_bps, "price_improvement_amount": improvement,
        "price_improvement_bps": improvement / reference * Decimal("10000"), "measurement_version": MEASUREMENT_VERSION,
        "arrival_price":reference,"decision_price":reference,"fees":fees,"fill_rate":fill_rate,"unfilled_quantity":order.quantity-order.filled_quantity,
        "quality_state":"MEASURED","evidence_hash": _hash({"order": order.id, "decision": decision.decision_id, "reference": reference, "execution": execution, "quantity": order.filled_quantity})})
    return report


def serialize_quality(row):
    return {"report_id": str(row.report_id), "order_id": str(row.order_id), "provider_id": row.routing_decision.selected_provider_id,
        "venue_id": row.routing_decision.selected_venue_id, "reference_price": str(row.reference_price), "execution_price": str(row.execution_price),
        "filled_quantity": str(row.filled_quantity), "slippage_bps": str(row.slippage_bps),
        "price_improvement_amount": str(row.price_improvement_amount), "price_improvement_bps": str(row.price_improvement_bps),
        "measurement_version": row.measurement_version, "simulation": row.order.simulation}


@transaction.atomic
def set_provider_halt(actor, provider_id, halted, reason):
    provider = ExecutionProviderRecord.objects.select_for_update().get(pk=provider_id)
    if provider.mode == "LIVE": raise ValueError("LIVE_EXECUTION_DISABLED")
    provider.health = "HALTED" if halted else "HEALTHY"
    provider.enabled = not halted
    provider.save(update_fields=("health", "enabled", "updated_at"))
    ApplicationAuditEvent.objects.create(actor_ref=str(actor.pk), action=f"execution.provider.{'halted' if halted else 'resumed'}",
        resource_type="execution_provider", resource_id=provider_id, request_id="operator", correlation_id=uuid.uuid4(),
        context={"mode": provider.mode}, reason=reason, occurred_at=timezone.now())
    enqueue_event(aggregate_type="execution_provider", aggregate_id=provider_id, event_type=f"execution.provider.{'halted' if halted else 'resumed'}.v1",
        payload={"provider_id": provider_id, "mode": provider.mode, "health": provider.health, "live": False}, tenant_ref="default")
    return provider


@transaction.atomic
def record_ambiguous_outcome(order, provider_id):
    """Fail closed after a possible provider submission; never select a fallback."""
    prior = order.routing_decisions.order_by("-created_at").first()
    if not prior: raise ValueError("ROUTING_DECISION_REQUIRED")
    decision = ExecutionRoutingDecision.objects.create(order=order, tenant_ref=order.tenant_ref, subject_ref=order.subject_ref,
        mode=prior.mode, status="UNKNOWN", selected_provider_id=provider_id, selected_venue_id=prior.selected_venue_id,
        policy_version=prior.policy_version, candidate_evidence=prior.candidate_evidence,
        exclusion_reasons=[{"provider_id": provider_id, "reasons": ["UNKNOWN_EXECUTION_OUTCOME", "RECONCILIATION_REQUIRED", "FAILOVER_PROHIBITED"]}],
        market_snapshot_hash=prior.market_snapshot_hash, request_hash=prior.request_hash, reference_price=prior.reference_price)
    enqueue_event(aggregate_type="execution", aggregate_id=order.id, event_type="execution.outcome.unknown.v1",
        payload={"order_id": str(order.id), "provider_id": provider_id, "reconciliation_required": True, "retry_allowed": False,
            "failover_allowed": False, "live": False}, tenant_ref=order.tenant_ref)
    provider=ExecutionProviderRecord.objects.get(pk=provider_id); venue=ExecutionVenue.objects.get(pk=prior.selected_venue_id)
    execution=CanonicalExecution.objects.create(order=order,provider=provider,venue=venue,state="UNKNOWN",quantity=order.quantity,
        filled_quantity=order.filled_quantity,remaining_quantity=order.quantity-order.filled_quantity,mode=prior.mode)
    UnknownExecutionOutcome.objects.create(execution=execution)
    return decision
