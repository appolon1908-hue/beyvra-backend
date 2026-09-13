"""Canonical, tenant-scoped PAPER trading application service.

All economic decisions in this module are made from explicit tenant context,
reference-data instruments, current market observations, fee schedules and
persisted account state.  The simulator never supplies fallback economics.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from prometheus_client import Counter, Histogram

from apps.compliance.domain import EligibilityResult
from apps.compliance.models import ComplianceAuditEvent, ComplianceProfile, EligibilityDecision
from apps.compliance.services import get_trading_eligibility
from apps.foundation.events import payload_hash
from apps.foundation.models import ApplicationAuditEvent, OutboxEvent, TradingControl
from apps.foundation.observability import (
    ENVIRONMENT,
    ORDER_DURATION,
    ORDERS,
    ORDERS_CANCELLED,
    ORDERS_FILLED,
    ORDERS_PARTIAL,
    ORDERS_REJECTED,
    RISK_DECISIONS,
    RISK_DURATION,
    SIM_RESERVATIONS,
    SIM_SETTLEMENT_DURATION,
    SIM_SETTLEMENTS,
)
from apps.foundation.services import (
    begin_idempotent_request,
    complete_idempotent_request,
    consume_once,
    enqueue_event,
)
from apps.post_trade.processor import process_simulated_fill
from apps.surveillance.engine import SurveillanceEngine
from apps.surveillance.services import persist_findings
from apps.trading.application.accounts import ensure_paper_identity, serialize_trading_account
from apps.trading.application.authorities import (
    FeeAuthority,
    MarketPriceAuthority,
    decimal_input,
    resolve_instrument,
    validate_instrument_values,
)
from apps.trading.application.context import TradingContext, require_trading_context
from apps.trading.domain.orders import OrderState, transition_order
from apps.trading.execution_authority import preview_route, record_quality
from apps.trading.models import (
    RiskDecision,
    SimulatedAccount,
    SimulatedPosition,
    SimulatedReservation,
    SimulatedTrade,
    TradingOrder,
)
from apps.trading.risk import RiskEngine
from integrations.execution.simulated import SimulatedExecutionProvider
from integrations.financial.simulated import SimulatedFinancialAdapter


SIMULATED_ORDERS = Counter("simulated_orders_total", "Simulation-only canonical orders", ("decision",))
SIMULATED_FILLS = Counter("simulated_fills_total", "Simulation-only executions")
SIMULATED_REJECTIONS = Counter("simulated_rejections_total", "Simulation-only rejected orders")
SIMULATED_CANCELLATIONS = Counter("simulated_cancellations_total", "Simulation-only cancelled orders")
SIMULATED_REPLACEMENTS = Counter("simulated_replacements_total", "Simulation-only replacements", ("result",))
SIMULATED_POSITION_COMMANDS = Counter("simulated_position_commands_total", "Simulation position commands", ("command", "result"))
SIMULATION_EXECUTION_LATENCY = Histogram("simulation_execution_latency_seconds", "Simulation-only execution processing latency")
SIMULATION_DUPLICATE_EVENTS = Counter("simulation_duplicate_event_count", "Duplicate simulation execution events ignored")
SIMULATION_ORDER_PROCESSING_LATENCY = Histogram("simulation_order_processing_latency_seconds", "Simulation-only order processing latency")


def simulation_available():
    return bool(
        settings.SIMULATED_TRADING_ENABLED
        and settings.DEPLOYMENT_ENV in {"local", "test", "staging"}
        and not settings.REAL_TRADING_ENABLED
        and not settings.EXTERNAL_EXECUTION_ENABLED
        and not settings.REAL_MONEY_ENABLED
        and not getattr(settings, "REAL_SETTLEMENT_ENABLED", False)
        and not getattr(settings, "LIVE_BROKER_ROUTING_ENABLED", False)
        and not getattr(settings, "FIX_LIVE_SESSION_ENABLED", False)
    )


def simulation_authorized(request):
    return (
        simulation_available()
        and request.user.is_authenticated
        and request.headers.get("X-Beyvra-Simulation-Mode", "").lower() == "true"
    )


def refs(value, tenant_ref=None):
    if isinstance(value, TradingContext):
        context = value
    elif tenant_ref is not None:
        context = TradingContext.for_user(value, tenant_ref)
    else:
        context = require_trading_context(value)
    return context.tenant_ref, context.subject_ref, context.account_ref


def correlation_uuid(value=None):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"beyvra:{value}") if value else uuid.uuid4()


def order_correlation(order):
    value = (
        OutboxEvent.objects.filter(
            aggregate_type="order",
            aggregate_id=str(order.id),
            event_type="trading.order.created.v1",
        )
        .values_list("correlation_id", flat=True)
        .first()
    )
    return correlation_uuid(value)


def compliance_decision(context, *, lock=False, persist=False):
    context = require_trading_context(context)
    profiles = ComplianceProfile.objects.filter(
        organization_id=context.organization_id,
        user_id=context.user_id,
    )
    if lock:
        profiles = profiles.select_for_update()
    profile = profiles.first()
    if profile is None:
        return None
    return get_trading_eligibility(
        profile,
        context_ref=context.account_ref,
        persist=persist,
    )


@transaction.atomic
def account_for(value, tenant_ref=None):
    context = value if isinstance(value, TradingContext) else (
        TradingContext.for_user(value, tenant_ref) if tenant_ref is not None else require_trading_context(value)
    )
    account, _ = SimulatedAccount.objects.get_or_create(
        tenant_ref=context.tenant_ref,
        subject_ref=context.subject_ref,
        account_ref=context.account_ref,
    )
    ensure_paper_identity(account)
    return account


def control_state(context, rules):
    scopes = (
        (TradingControl.Scope.ACCOUNT, context.account_ref),
        (TradingControl.Scope.INSTRUMENT, str(rules.instrument.instrument_id)),
        (TradingControl.Scope.ASSET_CLASS, rules.instrument.asset_class),
        (TradingControl.Scope.PLATFORM, "*"),
    )
    states = []
    for scope, scope_ref in scopes:
        row = TradingControl.objects.filter(scope=scope, scope_ref=scope_ref).first()
        if row:
            states.append(row.state)
    priority = ("HALTED", "MAINTENANCE", "CANCEL_ONLY", "CLOSE_ONLY", "ACTIVE")
    return next((state for state in priority if state in states), "ACTIVE")


def _current_position(account, instrument_id):
    return (
        SimulatedPosition.objects.filter(account=account, instrument_id=str(instrument_id))
        .values_list("quantity", flat=True)
        .first()
        or Decimal("0")
    )


def _account_risk_state(account, instrument_id):
    today = timezone.localdate()
    trades = SimulatedTrade.objects.filter(
        order__tenant_ref=account.tenant_ref,
        order__account_ref=account.account_ref,
        executed_at__date=today,
    )
    daily_notional = sum((row.quantity * row.price for row in trades.only("quantity", "price")), Decimal("0"))
    realized_daily_pnl = trades.aggregate(value=Sum("realized_pnl"))["value"] or Decimal("0")
    reserved_balance = (
        account.reservations.filter(
            state=SimulatedReservation.State.ACTIVE,
            asset=account.quote_currency,
        ).aggregate(value=Sum("remaining_amount"))["value"]
        or Decimal("0")
    )
    reserved_position = (
        account.reservations.filter(
            state=SimulatedReservation.State.ACTIVE,
            asset=str(instrument_id),
        ).aggregate(value=Sum("remaining_amount"))["value"]
        or Decimal("0")
    )
    open_orders = TradingOrder.objects.filter(
        tenant_ref=account.tenant_ref,
        account_ref=account.account_ref,
        state__in=("PENDING", "ACCEPTED", "OPEN", "PARTIALLY_FILLED"),
    ).count()
    return {
        "daily_notional": daily_notional,
        "realized_daily_loss": abs(min(realized_daily_pnl, Decimal("0"))),
        "reserved_balance": reserved_balance,
        "reserved_position": reserved_position,
        "open_order_count": open_orders,
    }


def normalized_payload(data):
    side = str(data.get("side") or "").upper()
    order_type = str(data.get("order_type") or "MARKET").upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError("INVALID_SIDE")
    if order_type not in {"MARKET", "LIMIT"}:
        raise ValueError("ORDER_TYPE_UNSUPPORTED")
    quantity = decimal_input(data.get("quantity"), field="quantity")
    limit_price = None
    if order_type == "LIMIT":
        if data.get("limit_price") is None:
            raise ValueError("LIMIT_PRICE_REQUIRED")
        limit_price = decimal_input(data.get("limit_price"), field="price")
    rules = resolve_instrument(data.get("instrument") or data.get("instrument_id"))
    validate_instrument_values(rules, quantity=quantity, limit_price=limit_price)
    evidence = MarketPriceAuthority.observe(rules.instrument)
    executable_price = evidence.executable_price(side)
    order_price = limit_price or executable_price
    notional = quantity * order_price
    if notional < rules.minimum_notional:
        raise ValueError("MIN_NOTIONAL_NOT_MET")
    if notional > rules.maximum_notional:
        raise ValueError("MAX_NOTIONAL_EXCEEDED")
    return {
        "instrument_id": str(rules.instrument.instrument_id),
        "instrument_symbol": rules.instrument.canonical_symbol,
        "instrument_version": rules.version.version,
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "price": executable_price,
        "order_price": order_price,
        "limit_price": limit_price,
        "notional": notional,
        "rules": rules,
        "price_evidence": evidence,
    }


def evaluate(
    value,
    data,
    *,
    persist_compliance=False,
    reservation_balance_credit=Decimal("0"),
    reservation_position_credit=Decimal("0"),
):
    context = require_trading_context(value)
    payload = normalized_payload(data)
    account = account_for(context)
    identity = ensure_paper_identity(account)
    financial = SimulatedFinancialAdapter()
    available = financial.available_quote(account) + reservation_balance_credit
    current_position = _current_position(account, payload["instrument_id"])
    risk_state = _account_risk_state(account, payload["instrument_id"])
    available_position = (
        current_position
        - risk_state["reserved_position"]
        + reservation_position_credit
    )
    projected_position = (
        current_position + payload["quantity"]
        if payload["side"] == "BUY"
        else available_position - payload["quantity"]
    )
    eligibility = compliance_decision(context, persist=persist_compliance)
    compliance_allowed = bool(eligibility and eligibility.result == EligibilityResult.ALLOWED)
    fees = FeeAuthority.calculate(
        context=context,
        rules=payload["rules"],
        side=payload["side"],
        order_type=payload["order_type"],
        quantity=payload["quantity"],
        notional=payload["notional"],
    )
    state = control_state(context, payload["rules"])
    risk_inputs = {
        "tenant_ref": context.tenant_ref,
        "account_ref": context.account_ref,
        "account_status": identity.status if identity.trading_enabled else "RESTRICTED",
        "simulation_eligible": True,
        "instrument_status": payload["rules"].instrument.status,
        "market_status": "OPEN",
        "side": payload["side"],
        "quantity": payload["quantity"],
        "min_quantity": payload["rules"].minimum_quantity,
        "max_quantity": payload["rules"].maximum_quantity,
        "notional": payload["notional"],
        "required_funds": payload["notional"] + (fees["total"] if payload["side"] == "BUY" else Decimal("0")),
        "min_notional": payload["rules"].minimum_notional,
        "max_notional": payload["rules"].maximum_notional,
        "available_funds": available,
        "reserved_balance": max(
            risk_state["reserved_balance"] - reservation_balance_credit,
            Decimal("0"),
        ),
        "current_position": current_position,
        "available_position": available_position,
        "reserved_position": max(
            risk_state["reserved_position"] - reservation_position_credit,
            Decimal("0"),
        ),
        "open_order_count": risk_state["open_order_count"],
        "projected_position": projected_position,
        "position_limit": payload["rules"].maximum_position,
        "daily_notional": risk_state["daily_notional"],
        "daily_notional_limit": payload["rules"].daily_notional_limit,
        "daily_loss": risk_state["realized_daily_loss"],
        "daily_loss_limit": payload["rules"].daily_loss_limit,
        "market_data_stale": False,
        "provider_health": payload["price_evidence"].provider_health,
        "compliance_eligible": compliance_allowed,
        "control_state": state,
        "reference_price": payload["price"],
        "order_price": payload["order_price"],
        "price_band_percent": payload["rules"].price_band_percent,
    }
    if state == "CANCEL_ONLY" or (state == "CLOSE_ONLY" and payload["side"] == "BUY"):
        risk_inputs["control_state"] = "HALTED"
    with RISK_DURATION.labels("true").time():
        risk = RiskEngine().evaluate_order(risk_inputs)
    reason = risk.reason_codes[0] if risk.reason_codes else "NONE"
    RISK_DECISIONS.labels(risk.decision, reason.lower(), risk.policy_version, "true").inc()
    surveillance = SurveillanceEngine().evaluate_order(
        tenant_ref=context.tenant_ref,
        account_ref=context.account_ref,
        payload=payload,
        asset_class=payload["rules"].instrument.asset_class,
        venue=payload["rules"].instrument.venue.code if payload["rules"].instrument.venue else "",
        market_data_stale=False,
    )
    return context, payload, account, risk, surveillance, eligibility, fees, available


def _price_dict(payload):
    evidence = payload["price_evidence"]
    return {
        "observation_id": str(evidence.observation_id),
        "bid": str(evidence.bid),
        "ask": str(evidence.ask),
        "mid": str(evidence.mid),
        "observed_at": evidence.observed_at.isoformat(),
        "stale_after": evidence.stale_after.isoformat(),
        "source": evidence.provider_id,
        "provider_health": evidence.provider_health,
    }


def _fee_dict(fees):
    return {
        "commission": str(fees["commission"]),
        "spread_cost": str(fees["spread_cost"]),
        "other_fees": str(fees["other_fees"]),
        "total": str(fees["total"]),
        "currency": fees["currency"],
        "schedule_version": fees["schedule_version"],
    }


def preview(value, data):
    context, payload, _account, risk, surveillance, _eligibility, fees, available = evaluate(value, data)
    decision = risk.decision if risk.decision != "ALLOW" else surveillance.decision
    reasons = list(risk.reason_codes if risk.decision != "ALLOW" else surveillance.reason_codes)
    return {
        "decision": decision,
        "reason_codes": reasons,
        "policy_version": risk.policy_version if risk.decision != "ALLOW" else surveillance.policy_version,
        "inputs_hash": risk.inputs_hash,
        "tenant_ref": context.tenant_ref,
        "account_ref": context.account_ref,
        "instrument": payload["instrument_id"],
        "instrument_symbol": payload["instrument_symbol"],
        "instrument_version": payload["instrument_version"],
        "side": payload["side"],
        "order_type": payload["order_type"],
        "quantity": str(payload["quantity"]),
        "price": str(payload["price"]),
        "notional": str(payload["notional"]),
        "price_evidence": _price_dict(payload),
        "fees": _fee_dict(fees),
        "estimated_fee": str(fees["total"]),
        "available_simulated_balance": str(available),
        "simulation": True,
    }


def event_payload(order, **extra):
    return {
        "tenant_ref": order.tenant_ref,
        "subject_ref": order.subject_ref,
        "account_ref": order.account_ref,
        "order_id": str(order.id),
        "instrument": order.instrument_id,
        "side": order.side,
        "quantity": str(order.quantity),
        "filled_quantity": str(order.filled_quantity),
        "state": order.state,
        "version": order.version,
        "simulation": True,
        "price_observation_id": str(order.price_observation_id) if order.price_observation_id else None,
        "price_source": order.price_source,
        "fee_schedule_version": order.fee_schedule_version,
        **extra,
    }


def audit_ref(context, action, resource_type, resource_id, correlation_id, reason="simulation", previous=None, new=None):
    context = require_trading_context(context)
    before = previous or {}
    after = new or {}
    return ApplicationAuditEvent.objects.create(
        actor_ref=context.subject_ref,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        before_hash=payload_hash(before) if before else "",
        after_hash=payload_hash(after) if after else "",
        request_id="simulation",
        correlation_id=correlation_uuid(correlation_id),
        context={
            "simulation": True,
            "tenant_ref": context.tenant_ref,
            "organization_id": str(context.organization_id),
            "account_ref": context.account_ref,
            "subject_ref": context.subject_ref,
            "previous_state": before,
            "new_state": after,
        },
        reason=reason,
        occurred_at=timezone.now(),
    )


def _persist_rejection(context, data, reason, correlation):
    rejected_id = uuid.uuid4()
    audit_ref(context, "simulation.order.rejected", "simulation_order_request", rejected_id, correlation, reason, new={"state": "REJECTED"})
    enqueue_event(
        aggregate_type="order_request",
        aggregate_id=rejected_id,
        event_type="trading.order.rejected.v1",
        payload={"tenant_ref": context.tenant_ref, "account_ref": context.account_ref, "reason_codes": [reason], "simulation": True},
        tenant_ref=context.tenant_ref,
        correlation_id=correlation,
    )


class _OrderRejected(Exception):
    def __init__(self, code, status, *, risk=None, eligibility=None):
        self.code = code
        self.status = status
        self.risk = risk
        self.eligibility = eligibility


def _record_rejected_create(context, data, idempotency_key, endpoint, correlation_id, rejection):
    with transaction.atomic():
        record, fresh = begin_idempotent_request(
            key=idempotency_key,
            tenant_ref=context.tenant_ref,
            actor_ref=f"{context.subject_ref}:{context.account_ref}",
            endpoint=endpoint,
            method="POST",
            request_data=data,
        )
        if fresh:
            if rejection.eligibility is not None:
                profile = ComplianceProfile.objects.get(
                    organization_id=context.organization_id,
                    user_id=context.user_id,
                )
                eligibility_row = EligibilityDecision.objects.create(
                    account=profile,
                    capability="TRADING",
                    result=rejection.eligibility.result,
                    reason_codes=list(rejection.eligibility.reason_codes),
                    policy_version=rejection.eligibility.policy_version,
                    evaluated_at=rejection.eligibility.evaluated_at,
                    context_ref=context.account_ref,
                )
                ComplianceAuditEvent.objects.create(
                    account=profile,
                    event_type="ELIGIBILITY_DECISION",
                    reason_codes=list(rejection.eligibility.reason_codes),
                    state_after={
                        "decision_id": str(eligibility_row.pk),
                        "capability": "TRADING",
                        "result": rejection.eligibility.result,
                    },
                    policy_version=rejection.eligibility.policy_version,
                )
            if rejection.risk is not None:
                risk_row = RiskDecision.objects.create(
                    tenant_ref=context.tenant_ref,
                    subject_ref=context.subject_ref,
                    account_ref=context.account_ref,
                    decision=rejection.risk.decision,
                    reason_codes=list(rejection.risk.reason_codes),
                    policy_version=rejection.risk.policy_version,
                    inputs_hash=rejection.risk.inputs_hash,
                )
                audit_ref(
                    context,
                    "simulation.risk.rejected",
                    "risk_decision",
                    risk_row.decision_id,
                    correlation_uuid(correlation_id),
                    rejection.code,
                    new={
                        "decision": rejection.risk.decision,
                        "reason_codes": list(rejection.risk.reason_codes),
                    },
                )
            _persist_rejection(context, data, rejection.code, correlation_uuid(correlation_id))
            complete_idempotent_request(
                record,
                status=rejection.status,
                body={"code": rejection.code},
                resource_type="simulation_order_request",
            )
            SIMULATED_REJECTIONS.inc()
            transaction.on_commit(lambda: ORDERS_REJECTED.labels(ENVIRONMENT, "true").inc())


def _create_attempt(value, data, idempotency_key, correlation_id=None, *, endpoint="/api/v1/trading/orders"):
    context = require_trading_context(value)
    if not idempotency_key:
        raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
    actor_scope = f"{context.subject_ref}:{context.account_ref}"
    with transaction.atomic():
        record, fresh = begin_idempotent_request(
            key=idempotency_key,
            tenant_ref=context.tenant_ref,
            actor_ref=actor_scope,
            endpoint=endpoint,
            method="POST",
            request_data=data,
        )
        if not fresh and record.response_body is not None:
            if record.response_status and record.response_status >= 400:
                raise _OrderRejected(record.response_body["code"], record.response_status)
            return record.response_body, record.response_status or 200
        account = account_for(context)
        SimulatedAccount.objects.select_for_update().get(pk=account.pk)
        context, payload, account, risk, surveillance, eligibility, fees, _available = evaluate(
            context,
            data,
            persist_compliance=True,
        )
        correlation = correlation_uuid(correlation_id)
        if eligibility is None or eligibility.result != EligibilityResult.ALLOWED:
            reason = eligibility.reason_codes[0] if eligibility and eligibility.reason_codes else "KYC_REQUIRED"
            _persist_rejection(context, data, reason, correlation)
            complete_idempotent_request(record, status=403, body={"code": reason}, resource_type="simulation_order_request")
            raise _OrderRejected(reason, 403, risk=risk, eligibility=eligibility)
        if risk.decision != "ALLOW":
            reason = risk.reason_codes[0] if risk.reason_codes else "ORDER_REVIEW_REQUIRED"
            _persist_rejection(context, data, reason, correlation)
            complete_idempotent_request(record, status=422, body={"code": reason}, resource_type="simulation_order_request")
            raise _OrderRejected(reason, 422, risk=risk, eligibility=eligibility)
        if surveillance.decision != "ALLOW":
            persist_findings(
                tenant_ref=context.tenant_ref,
                account_ref=context.account_ref,
                instrument_id=payload["instrument_id"],
                findings=surveillance.findings,
                actor_ref=context.subject_ref,
            )
            reason = surveillance.reason_codes[0] if surveillance.reason_codes else "ORDER_REJECTED"
            _persist_rejection(context, data, reason, correlation)
            complete_idempotent_request(record, status=422, body={"code": reason}, resource_type="simulation_order_request")
            raise _OrderRejected(reason, 422, risk=risk, eligibility=eligibility)
        evidence = payload["price_evidence"]
        order = TradingOrder.objects.create(
            tenant_ref=context.tenant_ref,
            subject_ref=context.subject_ref,
            account_ref=context.account_ref,
            instrument_id=payload["instrument_id"],
            order_type=payload["order_type"],
            side=payload["side"],
            quantity=payload["quantity"],
            limit_price=payload["limit_price"],
            reference_price=payload["price"],
            price_observation_id=evidence.observation_id,
            price_source=evidence.provider_id,
            price_observed_at=evidence.observed_at,
            price_stale_after=evidence.stale_after,
            fee_amount=fees["total"],
            fee_schedule_version=fees["schedule_version"],
            eligibility_policy_version=eligibility.policy_version,
            eligibility_result=eligibility.result,
            eligibility_reason_codes=list(eligibility.reason_codes),
            eligibility_evaluated_at=eligibility.evaluated_at,
            idempotency_key=idempotency_key,
            state=OrderState.PENDING,
            simulation=True,
        )
        route = preview_route(
            context.user,
            {
                "instrument": payload["instrument_id"],
                "side": payload["side"],
                "order_type": payload["order_type"],
                "quantity": str(payload["quantity"]),
                "reference_price": str(payload["price"]),
                "limit_price": str(payload["limit_price"]) if payload["limit_price"] is not None else None,
                "asset_class": payload["rules"].instrument.asset_class,
                "fees": _fee_dict(fees),
                "market_source": evidence.provider_id,
                "risk_snapshot_hash": risk.inputs_hash,
                "tenant_ref": context.tenant_ref,
                "subject_ref": context.subject_ref,
                "mode": "SIMULATION",
                "correlation_id": str(correlation),
            },
            persist=True,
            order=order,
        )
        if not route["routable"]:
            raise ValueError("ORDER_NOT_ROUTABLE")
        risk_row = RiskDecision.objects.create(
            tenant_ref=context.tenant_ref,
            subject_ref=context.subject_ref,
            account_ref=context.account_ref,
            order_id=order.id,
            decision=risk.decision,
            reason_codes=list(risk.reason_codes),
            policy_version=risk.policy_version,
            inputs_hash=risk.inputs_hash,
        )
        order.risk_decision_id = risk_row.decision_id
        reservation = SimulatedFinancialAdapter().reserve_funds(
            account=account,
            order_id=order.id,
            instrument_id=order.instrument_id,
            side=order.side,
            quantity=order.quantity,
            price=payload["order_price"],
            fee=fees["total"],
        )
        order.reservation_id = reservation.id
        order.save(update_fields=("risk_decision_id", "reservation_id", "updated_at"))
        audit_ref(context, "simulation.risk.decided", "risk_decision", risk_row.decision_id, correlation, risk.decision, new={"decision": risk.decision})
        audit_ref(context, "simulation.order.created", "simulation_order", order.id, correlation, "accepted", new={"state": order.state, "version": order.version})
        enqueue_event(
            aggregate_type="order",
            aggregate_id=order.id,
            event_type="trading.order.created.v1",
            payload=event_payload(order),
            tenant_ref=context.tenant_ref,
            correlation_id=correlation,
        )
        enqueue_event(
            aggregate_type="execution",
            aggregate_id=order.id,
            event_type="trading.execution.submitted.v1",
            payload=event_payload(order, execution_mode="SIMULATION"),
            tenant_ref=context.tenant_ref,
            correlation_id=correlation,
        )
        SIMULATED_ORDERS.labels(decision=risk.decision).inc()
        transaction.on_commit(lambda: SIM_RESERVATIONS["created"].inc())
        transaction.on_commit(lambda: ORDERS.labels(ENVIRONMENT, "true").inc())
        body = serialize_order(order)
        complete_idempotent_request(record, status=201, body=body, resource_type="simulation_order", resource_id=order.id)
        if settings.SIMULATED_EXECUTION_INLINE:
            transaction.on_commit(lambda: process_created_order(order.id))
        return body, 201


def create(value, data, idempotency_key, correlation_id=None, *, endpoint="/api/v1/trading/orders"):
    context = require_trading_context(value)
    try:
        return _create_attempt(context, data, idempotency_key, correlation_id, endpoint=endpoint)
    except _OrderRejected as rejection:
        _record_rejected_create(context, data, idempotency_key, endpoint, correlation_id, rejection)
        raise ValueError(rejection.code)


@SIMULATION_EXECUTION_LATENCY.time()
@transaction.atomic
def apply_execution(order_id, execution):
    order = TradingOrder.objects.select_for_update().get(pk=order_id, simulation=True)
    correlation = order_correlation(order)
    envelope = {
        "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, execution.execution_id)),
        "correlation_id": str(correlation),
        "payload": {
            "execution_id": execution.execution_id,
            "order_id": str(order.id),
            "quantity": str(execution.quantity),
            "price": str(execution.price),
            "outcome": execution.outcome,
        },
    }

    def mutation():
        nonlocal order
        context = TradingContext.for_user(get_user_model().objects.get(pk=order.subject_ref), order.tenant_ref)
        previous = {"state": order.state, "filled_quantity": str(order.filled_quantity), "version": order.version}
        enqueue_event(
            aggregate_type="execution",
            aggregate_id=execution.execution_id,
            event_type="trading.execution.received.v1",
            payload=event_payload(order, execution_id=execution.execution_id, outcome=execution.outcome),
            tenant_ref=order.tenant_ref,
            correlation_id=correlation,
        )
        if execution.outcome == "REJECT":
            order.state = transition_order(order.state, "REJECTED")
            SimulatedFinancialAdapter().release_reservation(SimulatedReservation.objects.get(pk=order.reservation_id))
            event_type = "trading.order.rejected.v1"
            transaction.on_commit(lambda: ORDERS_REJECTED.labels(ENVIRONMENT, "true").inc())
        elif execution.outcome == "EXPIRE":
            if order.state == "PENDING":
                order.state = transition_order(order.state, "ACCEPTED")
            if order.state == "ACCEPTED":
                order.state = transition_order(order.state, "OPEN")
            order.state = transition_order(order.state, "EXPIRED")
            SimulatedFinancialAdapter().release_reservation(SimulatedReservation.objects.get(pk=order.reservation_id))
            event_type = "trading.order.expired.v1"
        else:
            if order.state == "PENDING":
                order.state = transition_order(order.state, "ACCEPTED")
            if order.state == "ACCEPTED":
                order.state = transition_order(order.state, "OPEN")
            next_filled = order.filled_quantity + execution.quantity
            if next_filled > order.quantity:
                raise ValueError("EXECUTION_OVERFILL")
            fee = order.fee_amount * execution.quantity / order.quantity
            reservation = SimulatedReservation.objects.get(pk=order.reservation_id)
            with SIM_SETTLEMENT_DURATION.time():
                account, position, _, realized_pnl = SimulatedFinancialAdapter().settle_trade(
                    reservation=reservation,
                    side=order.side,
                    instrument_id=order.instrument_id,
                    quantity=execution.quantity,
                    price=execution.price,
                    fee=fee,
                )
            reservation.refresh_from_db()
            if reservation.state == SimulatedReservation.State.CONSUMED:
                transaction.on_commit(lambda: SIM_RESERVATIONS["consumed"].inc())
            executed_at = timezone.now()
            SimulatedTrade.objects.create(
                order=order,
                execution_id=execution.execution_id,
                instrument_id=order.instrument_id,
                side=order.side,
                quantity=execution.quantity,
                price=execution.price,
                fee=fee,
                realized_pnl=realized_pnl,
                executed_at=executed_at,
            )
            process_simulated_fill(
                order=order,
                execution_id=execution.execution_id,
                quantity=execution.quantity,
                price=execution.price,
                fee=fee,
                executed_at=executed_at,
            )
            previous_value = order.filled_quantity * (order.average_fill_price or Decimal("0"))
            order.filled_quantity = next_filled
            order.average_fill_price = (previous_value + execution.quantity * execution.price) / next_filled
            order.state = transition_order(order.state, "FILLED" if next_filled == order.quantity else "PARTIALLY_FILLED")
            state_metric = ORDERS_FILLED if order.state == "FILLED" else ORDERS_PARTIAL
            transaction.on_commit(lambda metric=state_metric: metric.labels(ENVIRONMENT, "true").inc())
            transaction.on_commit(lambda: SIM_SETTLEMENTS.labels("success").inc())
            SIMULATED_FILLS.inc()
            event_type = "trading.order.filled.v1" if order.state == "FILLED" else "trading.order.partially_filled.v1"
            enqueue_event(
                aggregate_type="trade",
                aggregate_id=execution.execution_id,
                event_type="trading.trade.executed.v1",
                payload=event_payload(order, execution_id=execution.execution_id, price=str(execution.price), fee=str(fee)),
                tenant_ref=order.tenant_ref,
                correlation_id=correlation,
            )
            enqueue_event(
                aggregate_type="position",
                aggregate_id=position.id,
                event_type="trading.position.updated.v1",
                payload={
                    "tenant_ref": order.tenant_ref,
                    "account_ref": order.account_ref,
                    "position_id": str(position.id),
                    "instrument": order.instrument_id,
                    "quantity": str(position.quantity),
                    "average_price": str(position.average_price),
                    "simulation": True,
                },
                tenant_ref=order.tenant_ref,
                correlation_id=correlation,
            )
            enqueue_event(
                aggregate_type="account",
                aggregate_id=account.id,
                event_type="trading.balance_projection.updated.v1",
                payload=serialize_account(account),
                tenant_ref=order.tenant_ref,
                correlation_id=correlation,
            )
        order.version += 1
        order.save(update_fields=("state", "filled_quantity", "average_fill_price", "version", "updated_at"))
        audit_ref(
            context,
            "simulation.execution.applied",
            "simulation_execution",
            execution.execution_id,
            correlation,
            execution.outcome,
            previous=previous,
            new={"state": order.state, "filled_quantity": str(order.filled_quantity), "version": order.version},
        )
        canonical_event = {"REJECT": "trading.execution.rejected.v1", "EXPIRE": "trading.execution.cancelled.v1"}.get(execution.outcome)
        if not canonical_event:
            canonical_event = "trading.execution.filled.v1" if order.state == "FILLED" else "trading.execution.partial_fill.v1"
        enqueue_event(
            aggregate_type="execution",
            aggregate_id=execution.execution_id,
            event_type=canonical_event,
            payload=event_payload(order, execution_id=execution.execution_id, execution_mode="SIMULATION"),
            tenant_ref=order.tenant_ref,
            correlation_id=correlation,
        )
        if order.filled_quantity:
            quality = record_quality(order)
            enqueue_event(
                aggregate_type="execution_quality",
                aggregate_id=quality.report_id,
                event_type="trading.execution.quality.updated.v1",
                payload={
                    "tenant_ref": order.tenant_ref,
                    "account_ref": order.account_ref,
                    "report_id": str(quality.report_id),
                    "order_id": str(order.id),
                    "slippage_bps": str(quality.slippage_bps),
                    "price_improvement_bps": str(quality.price_improvement_bps),
                    "simulation": True,
                },
                tenant_ref=order.tenant_ref,
                correlation_id=correlation,
            )
        enqueue_event(
            aggregate_type="order",
            aggregate_id=order.id,
            event_type=event_type,
            payload=event_payload(order),
            tenant_ref=order.tenant_ref,
            correlation_id=correlation,
        )

    consumed = consume_once(envelope=envelope, consumer_name="simulated-execution-v1", mutation=mutation)
    if not consumed:
        SIMULATION_DUPLICATE_EVENTS.inc()
    return consumed


@SIMULATION_ORDER_PROCESSING_LATENCY.time()
@ORDER_DURATION.labels(ENVIRONMENT, "true").time()
@transaction.atomic
def process_created_order(order_id, scenario=None):
    order = TradingOrder.objects.select_for_update().get(pk=order_id, simulation=True)
    correlation = order_correlation(order)
    selected = scenario or settings.SIMULATED_EXECUTION_SCENARIO
    if order.state == "PENDING" and selected != "REJECT":
        order.state = transition_order(order.state, "ACCEPTED")
        order.version += 1
        order.save(update_fields=("state", "version", "updated_at"))
        enqueue_event(
            aggregate_type="order",
            aggregate_id=order.id,
            event_type="trading.order.accepted.v1",
            payload=event_payload(order),
            tenant_ref=order.tenant_ref,
            correlation_id=correlation,
        )
    for execution in SimulatedExecutionProvider(selected).submit_order(order):
        apply_execution(order.id, execution)
    order.refresh_from_db()
    if order.state == "ACCEPTED":
        order.state = transition_order(order.state, "OPEN")
        order.version += 1
        order.save(update_fields=("state", "version", "updated_at"))
        enqueue_event(
            aggregate_type="order",
            aggregate_id=order.id,
            event_type="trading.order.opened.v1",
            payload=event_payload(order),
            tenant_ref=order.tenant_ref,
            correlation_id=correlation,
        )
    return order


def _version_matches(order, expected_version):
    value = str(expected_version or "").strip().strip('"')
    return value == str(order.version) or value == order.updated_at.isoformat()


def _context_order(context, order_id, *, lock=False):
    rows = TradingOrder.objects.filter(
        pk=order_id,
        tenant_ref=context.tenant_ref,
        account_ref=context.account_ref,
        simulation=True,
    )
    return rows.select_for_update().get() if lock else rows.get()


def _record_failed_command(context, *, key, endpoint, request_data, code, status=409):
    if not key:
        return
    with transaction.atomic():
        record, fresh = begin_idempotent_request(
            key=key,
            tenant_ref=context.tenant_ref,
            actor_ref=f"{context.subject_ref}:{context.account_ref}",
            endpoint=endpoint,
            method="POST",
            request_data=request_data,
        )
        if fresh:
            complete_idempotent_request(record, status=status, body={"code": code}, resource_type="simulation_command")


def _cancel_attempt(value, order_id, idempotency_key, expected_version, correlation_id=None):
    context = require_trading_context(value)
    if not idempotency_key:
        raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
    if not expected_version:
        raise ValueError("IF_MATCH_REQUIRED")
    endpoint = f"/api/v1/trading/orders/{order_id}/cancel"
    actor_scope = f"{context.subject_ref}:{context.account_ref}"
    with transaction.atomic():
        record, fresh = begin_idempotent_request(
            key=idempotency_key,
            tenant_ref=context.tenant_ref,
            actor_ref=actor_scope,
            endpoint=endpoint,
            method="POST",
            request_data={"order_id": str(order_id), "expected_version": str(expected_version)},
        )
        if not fresh and record.response_body is not None:
            if record.response_status and record.response_status >= 400:
                raise ValueError(record.response_body["code"])
            return record.response_body
        order = _context_order(context, order_id, lock=True)
        if not _version_matches(order, expected_version):
            complete_idempotent_request(record, status=409, body={"code": "VERSION_CONFLICT"}, resource_type="simulation_order", resource_id=order.id)
            raise ValueError("VERSION_CONFLICT")
        if order.state not in {"ACCEPTED", "OPEN", "PARTIALLY_FILLED"}:
            raise ValueError("ORDER_INVALID_STATE")
        previous = {"state": order.state, "version": order.version}
        correlation = correlation_uuid(correlation_id) if correlation_id else order_correlation(order)
        order.state = transition_order(order.state, "CANCEL_PENDING")
        order.version += 1
        order.save(update_fields=("state", "version", "updated_at"))
        enqueue_event(
            aggregate_type="order",
            aggregate_id=order.id,
            event_type="trading.order.cancel_requested.v1",
            payload=event_payload(order),
            tenant_ref=context.tenant_ref,
            correlation_id=correlation,
        )
        order.state = transition_order(order.state, "CANCELLED")
        order.version += 1
        order.save(update_fields=("state", "version", "updated_at"))
        if order.reservation_id:
            SimulatedFinancialAdapter().release_reservation(SimulatedReservation.objects.get(pk=order.reservation_id))
        enqueue_event(
            aggregate_type="order",
            aggregate_id=order.id,
            event_type="trading.order.cancelled.v1",
            payload=event_payload(order),
            tenant_ref=context.tenant_ref,
            correlation_id=correlation,
        )
        audit_ref(context, "simulation.order.cancelled", "simulation_order", order.id, correlation, "cancelled", previous=previous, new={"state": order.state, "version": order.version})
        transaction.on_commit(lambda: SIM_RESERVATIONS["released"].inc())
        transaction.on_commit(lambda: ORDERS_CANCELLED.labels(ENVIRONMENT, "true").inc())
        SIMULATED_CANCELLATIONS.inc()
        body = serialize_order(order)
        complete_idempotent_request(record, status=200, body=body, resource_type="simulation_order", resource_id=order.id)
        return body


def cancel(value, order_id, idempotency_key, expected_version, correlation_id=None):
    context = require_trading_context(value)
    endpoint = f"/api/v1/trading/orders/{order_id}/cancel"
    request_data = {"order_id": str(order_id), "expected_version": str(expected_version)}
    try:
        return _cancel_attempt(context, order_id, idempotency_key, expected_version, correlation_id)
    except ValueError as error:
        _record_failed_command(context, key=idempotency_key, endpoint=endpoint, request_data=request_data, code=str(error))
        raise


def _replace_attempt(value, order_id, data, idempotency_key, expected_version, correlation_id=None):
    context = require_trading_context(value)
    if not idempotency_key:
        raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
    if not expected_version:
        raise ValueError("IF_MATCH_REQUIRED")
    unexpected = set(data) - {"limit_price"}
    if unexpected or data.get("limit_price") is None:
        raise ValueError("REPLACE_PRICE_ONLY")
    endpoint = f"/api/v1/trading/orders/{order_id}/replace"
    actor_scope = f"{context.subject_ref}:{context.account_ref}"
    with transaction.atomic():
        record, fresh = begin_idempotent_request(
            key=idempotency_key,
            tenant_ref=context.tenant_ref,
            actor_ref=actor_scope,
            endpoint=endpoint,
            method="POST",
            request_data={"order_id": str(order_id), "limit_price": data.get("limit_price"), "expected_version": str(expected_version)},
        )
        if not fresh and record.response_body is not None:
            if record.response_status and record.response_status >= 400:
                raise ValueError(record.response_body["code"])
            return record.response_body
        order = _context_order(context, order_id, lock=True)
        if not _version_matches(order, expected_version):
            raise ValueError("VERSION_CONFLICT")
        if order.order_type != "LIMIT":
            raise ValueError("REPLACE_LIMIT_ONLY")
        if order.state not in {"ACCEPTED", "OPEN"} or order.filled_quantity:
            raise ValueError("ORDER_INVALID_STATE")
        reservation = SimulatedReservation.objects.select_for_update().get(pk=order.reservation_id)
        candidate = {
            "instrument": order.instrument_id,
            "side": order.side,
            "order_type": order.order_type,
            "quantity": str(order.quantity),
            "limit_price": data.get("limit_price"),
        }
        _context, payload, account, risk, surveillance, eligibility, fees, _available = evaluate(
            context,
            candidate,
            persist_compliance=True,
            reservation_balance_credit=(
                reservation.remaining_amount if order.side == "BUY" else Decimal("0")
            ),
            reservation_position_credit=(
                reservation.remaining_amount if order.side == "SELL" else Decimal("0")
            ),
        )
        if eligibility is None or eligibility.result != EligibilityResult.ALLOWED:
            raise ValueError(eligibility.reason_codes[0] if eligibility and eligibility.reason_codes else "KYC_REQUIRED")
        if risk.decision != "ALLOW":
            raise ValueError(risk.reason_codes[0] if risk.reason_codes else "ORDER_REVIEW_REQUIRED")
        if surveillance.decision != "ALLOW":
            raise ValueError(surveillance.reason_codes[0] if surveillance.reason_codes else "ORDER_REJECTED")
        if order.side == "BUY":
            required = order.quantity * payload["order_price"] + fees["total"]
            if required > reservation.original_amount:
                complete_idempotent_request(record, status=409, body={"code": "RESERVATION_INCREASE_REQUIRED"}, resource_type="simulation_order", resource_id=order.id)
                SIMULATED_REPLACEMENTS.labels("denied_increase").inc()
                raise ValueError("RESERVATION_INCREASE_REQUIRED")
            reservation.original_amount = required
            reservation.remaining_amount = required
            reservation.save(update_fields=("original_amount", "remaining_amount", "updated_at"))
        previous = {"limit_price": str(order.limit_price), "version": order.version}
        order.limit_price = payload["limit_price"]
        order.reference_price = payload["price"]
        order.price_observation_id = payload["price_evidence"].observation_id
        order.price_source = payload["price_evidence"].provider_id
        order.price_observed_at = payload["price_evidence"].observed_at
        order.price_stale_after = payload["price_evidence"].stale_after
        order.fee_amount = fees["total"]
        order.fee_schedule_version = fees["schedule_version"]
        order.version += 1
        order.save(update_fields=(
            "limit_price", "reference_price", "price_observation_id", "price_source", "price_observed_at",
            "price_stale_after", "fee_amount", "fee_schedule_version", "version", "updated_at",
        ))
        correlation = correlation_uuid(correlation_id) if correlation_id else order_correlation(order)
        audit_ref(context, "simulation.order.replaced", "simulation_order", order.id, correlation, "price_replaced", previous=previous, new={"limit_price": str(order.limit_price), "version": order.version})
        enqueue_event(
            aggregate_type="order",
            aggregate_id=order.id,
            event_type="trading.order.replaced.v1",
            payload=event_payload(order, previous_limit_price=previous["limit_price"]),
            tenant_ref=context.tenant_ref,
            correlation_id=correlation,
        )
        body = serialize_order(order)
        complete_idempotent_request(record, status=200, body=body, resource_type="simulation_order", resource_id=order.id)
        SIMULATED_REPLACEMENTS.labels("success").inc()
        return body


def replace(value, order_id, data, idempotency_key, expected_version, correlation_id=None):
    context = require_trading_context(value)
    endpoint = f"/api/v1/trading/orders/{order_id}/replace"
    request_data = {"order_id": str(order_id), "limit_price": data.get("limit_price"), "expected_version": str(expected_version)}
    try:
        return _replace_attempt(context, order_id, data, idempotency_key, expected_version, correlation_id)
    except ValueError as error:
        _record_failed_command(context, key=idempotency_key, endpoint=endpoint, request_data=request_data, code=str(error))
        raise


def position_order(value, position_id, *, command, quantity=None, idempotency_key, correlation_id=None):
    context = require_trading_context(value)
    if command not in {"close", "reduce"}:
        raise ValueError("POSITION_COMMAND_UNSUPPORTED")
    if not idempotency_key:
        raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
    endpoint = f"/api/v1/trading/positions/{position_id}/{command}"
    command_payload = {
        "position_id": str(position_id),
        "command": command,
        "quantity": None if command == "close" else quantity,
    }
    with transaction.atomic():
        command_record, fresh = begin_idempotent_request(
            key=idempotency_key,
            tenant_ref=context.tenant_ref,
            actor_ref=f"{context.subject_ref}:{context.account_ref}",
            endpoint=endpoint,
            method="POST",
            request_data=command_payload,
        )
        if not fresh and command_record.response_body is not None:
            if command_record.response_status and command_record.response_status >= 400:
                raise ValueError(command_record.response_body["code"])
            return command_record.response_body, command_record.response_status or 200
        account = account_for(context)
        SimulatedAccount.objects.select_for_update().get(pk=account.pk)
        position = SimulatedPosition.objects.select_for_update().filter(
            pk=position_id,
            account=account,
        ).first()
        if position is None:
            raise SimulatedPosition.DoesNotExist
        if position.quantity <= 0:
            raise ValueError("POSITION_NOT_LONG")
        reduction = position.quantity if command == "close" else decimal_input(quantity, field="quantity")
        if reduction > position.quantity:
            raise ValueError("POSITION_REDUCTION_EXCEEDS_AVAILABLE")
        body, status = create(
            context,
            {
                "instrument": position.instrument_id,
                "side": "SELL",
                "order_type": "MARKET",
                "quantity": str(reduction),
            },
            idempotency_key,
            correlation_id,
            endpoint=f"{endpoint}/order",
        )
        event_type = f"trading.position.{command}_requested.v1"
        already_recorded = OutboxEvent.objects.filter(
            aggregate_type="position",
            aggregate_id=str(position.id),
            event_type=event_type,
            payload__order_id=body["id"],
        ).exists()
        if not already_recorded:
            correlation = correlation_uuid(correlation_id)
            enqueue_event(
                aggregate_type="position",
                aggregate_id=position.id,
                event_type=event_type,
                payload={
                    "tenant_ref": context.tenant_ref,
                    "account_ref": context.account_ref,
                    "position_id": str(position.id),
                    "order_id": body["id"],
                    "quantity": str(reduction),
                    "simulation": True,
                },
                tenant_ref=context.tenant_ref,
                correlation_id=correlation,
            )
            audit_ref(
                context,
                f"simulation.position.{command}_requested",
                "simulation_position",
                position.id,
                correlation,
                command,
                new={"order_id": body["id"], "quantity": str(reduction)},
            )
            SIMULATED_POSITION_COMMANDS.labels(command, "success").inc()
        complete_idempotent_request(
            command_record,
            status=status,
            body=body,
            resource_type="simulation_order",
            resource_id=body["id"],
        )
        return body, status


def serialize_order(order):
    return {
        "id": str(order.id),
        "tenant_ref": order.tenant_ref,
        "account_ref": order.account_ref,
        "instrument": order.instrument_id,
        "side": order.side,
        "order_type": order.order_type,
        "quantity": str(order.quantity),
        "limit_price": str(order.limit_price) if order.limit_price is not None else None,
        "reference_price": str(order.reference_price) if order.reference_price is not None else None,
        "filled_quantity": str(order.filled_quantity),
        "average_fill_price": str(order.average_fill_price) if order.average_fill_price is not None else None,
        "state": order.state,
        "version": order.version,
        "price_evidence": {
            "observation_id": str(order.price_observation_id) if order.price_observation_id else None,
            "source": order.price_source,
            "observed_at": order.price_observed_at.isoformat() if order.price_observed_at else None,
            "stale_after": order.price_stale_after.isoformat() if order.price_stale_after else None,
        },
        "fees": {"total": str(order.fee_amount), "schedule_version": order.fee_schedule_version},
        "simulation": True,
        "eligibility_policy_version": order.eligibility_policy_version,
        "eligibility_result": order.eligibility_result,
        "eligibility_reason_codes": order.eligibility_reason_codes,
        "eligibility_evaluated_at": order.eligibility_evaluated_at.isoformat() if order.eligibility_evaluated_at else None,
    }


def serialize_account(account):
    reserved = (
        account.reservations.filter(state=SimulatedReservation.State.ACTIVE)
        .aggregate(total=Sum("remaining_amount"))["total"]
        or Decimal("0")
    )
    return {
        "id": str(account.id),
        "tenant_ref": account.tenant_ref,
        "account_ref": account.account_ref,
        "currency": account.quote_currency,
        "total": str(account.total_balance),
        "available": str(SimulatedFinancialAdapter.available_quote(account)),
        "reserved": str(reserved),
        "pending": str(account.pending_balance),
        "simulation": True,
        **serialize_trading_account(ensure_paper_identity(account)),
    }
