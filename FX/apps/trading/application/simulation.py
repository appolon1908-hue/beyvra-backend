import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.foundation.models import ApplicationAuditEvent, TradingControl
from apps.foundation.services import begin_idempotent_request, complete_idempotent_request, consume_once, enqueue_event
from apps.trading.domain.orders import OrderState, transition_order
from apps.trading.models import RiskDecision, SimulatedAccount, SimulatedPosition, SimulatedReservation, SimulatedTrade, TradingOrder
from apps.trading.risk import RiskEngine
from integrations.execution.simulated import SimulatedExecutionProvider
from integrations.financial.simulated import SimulatedFinancialAdapter
from prometheus_client import Counter, Histogram

FEE_RATE = Decimal("0.001")
SIMULATED_ORDERS = Counter("simulated_orders_total", "Simulation-only canonical orders", ("decision",))
SIMULATED_FILLS = Counter("simulated_fills_total", "Simulation-only executions")
SIMULATED_REJECTIONS = Counter("simulated_rejections_total", "Simulation-only rejected orders")
SIMULATED_CANCELLATIONS = Counter("simulated_cancellations_total", "Simulation-only cancelled orders")
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
    )


def simulation_authorized(request):
    # Authority is server-side environment gating plus an authenticated caller's
    # explicit simulation intent. No deploy secret is ever shipped to a browser.
    return (
        simulation_available()
        and request.user.is_authenticated
        and request.headers.get("X-Beyvra-Simulation-Mode", "").lower() == "true"
    )


def refs(user):
    subject = str(user.pk)
    return "default", subject, f"sim:{subject}"


def account_for(user):
    tenant, subject, account_ref = refs(user)
    account, _ = SimulatedAccount.objects.get_or_create(tenant_ref=tenant, subject_ref=subject, account_ref=account_ref)
    return account


def control_state(instrument_id):
    controls = TradingControl.objects.filter(scope__in=("PLATFORM", "INSTRUMENT"), scope_ref__in=("*", instrument_id)).order_by("-created_at")
    return controls.first().state if controls.exists() else "ACTIVE"


def normalized_payload(data):
    try:
        instrument = str(data.get("instrument") or data.get("instrument_id") or "").upper()
        side = str(data.get("side") or "").upper()
        order_type = str(data.get("order_type") or "MARKET").upper()
        quantity = Decimal(str(data.get("quantity")))
        price = Decimal(str(settings.SIMULATED_EXECUTION_PRICES[instrument]))
    except (KeyError, InvalidOperation, TypeError):
        raise ValueError("VALIDATION_ERROR")
    if side not in {"BUY", "SELL"} or order_type not in {"MARKET", "LIMIT"} or quantity <= 0:
        raise ValueError("VALIDATION_ERROR")
    return {"instrument_id": instrument, "side": side, "order_type": order_type, "quantity": quantity, "price": price}


def evaluate(user, data):
    payload = normalized_payload(data)
    account = account_for(user)
    financial = SimulatedFinancialAdapter()
    available = financial.available_quote(account)
    notional = payload["quantity"] * payload["price"]
    state = control_state(payload["instrument_id"])
    inputs = {"account_status": account.status, "simulation_eligible": True, "instrument_status": "ACTIVE", "market_status": "OPEN", "side": payload["side"], "quantity": payload["quantity"], "min_quantity": "0.0001", "max_quantity": "100", "notional": notional, "min_notional": "1", "max_notional": "1000000", "available_funds": available if payload["side"] == "BUY" else Decimal("Infinity"), "projected_position": payload["quantity"], "position_limit": "100", "daily_notional": "0", "daily_notional_limit": "1000000", "daily_loss": "0", "daily_loss_limit": "10000", "market_data_stale": settings.SIMULATED_MARKET_DATA_STALE, "provider_health": "HEALTHY", "compliance_eligible": True, "control_state": state, "reference_price": payload["price"], "order_price": payload["price"], "price_band_percent": "5"}
    if state == "CANCEL_ONLY" or (state == "CLOSE_ONLY" and payload["side"] == "BUY"):
        inputs["control_state"] = "HALTED"
    result = RiskEngine().evaluate_order(inputs)
    return payload, account, result, available, notional


def preview(user, data):
    payload, account, result, available, notional = evaluate(user, data)
    return {"decision": result.decision, "reason_codes": list(result.reason_codes), "policy_version": result.policy_version, "inputs_hash": result.inputs_hash, "instrument": payload["instrument_id"], "side": payload["side"], "order_type": payload["order_type"], "quantity": str(payload["quantity"]), "price": str(payload["price"]), "notional": str(notional), "estimated_fee": str(notional * FEE_RATE), "available_simulated_balance": str(available), "simulation": True}


def event_payload(order, **extra):
    return {"order_id": str(order.id), "account_ref": order.account_ref, "instrument": order.instrument_id, "side": order.side, "quantity": str(order.quantity), "filled_quantity": str(order.filled_quantity), "state": order.state, "simulation": True, "price_source": settings.SIMULATED_EXECUTION_PRICE_SOURCE, **extra}


def audit(user, action, resource_id, correlation_id, reason="simulation"):
    return ApplicationAuditEvent.objects.create(actor_ref=str(user.pk), action=action, resource_type="simulation_order", resource_id=str(resource_id), request_id="simulation", correlation_id=correlation_id, context={"simulation": True}, reason=reason, occurred_at=timezone.now())


def audit_ref(actor_ref, action, resource_type, resource_id, correlation_id, reason="simulation"):
    return ApplicationAuditEvent.objects.create(actor_ref=str(actor_ref), action=action, resource_type=resource_type, resource_id=str(resource_id), request_id="simulation", correlation_id=correlation_id, context={"simulation": True}, reason=reason, occurred_at=timezone.now())


@transaction.atomic
def create(user, data, idempotency_key):
    tenant, subject, account_ref = refs(user)
    payload, account, result, _available, _notional = evaluate(user, data)
    if result.decision != "ALLOW":
        raise ValueError(result.reason_codes[0] if result.reason_codes else "ORDER_REVIEW_REQUIRED")
    record, fresh = begin_idempotent_request(key=idempotency_key, tenant_ref=tenant, actor_ref=subject, endpoint="/api/v1/trading/orders", method="POST", request_data=data)
    if not fresh and record.response_body is not None:
        return record.response_body, record.response_status
    order = TradingOrder.objects.create(tenant_ref=tenant, subject_ref=subject, account_ref=account_ref, instrument_id=payload["instrument_id"], order_type=payload["order_type"], side=payload["side"], quantity=payload["quantity"], state=OrderState.PENDING, simulation=True)
    risk = RiskDecision.objects.create(tenant_ref=tenant, subject_ref=subject, account_ref=account_ref, order_id=order.id, decision=result.decision, reason_codes=list(result.reason_codes), policy_version=result.policy_version, inputs_hash=result.inputs_hash)
    correlation = uuid.uuid4()
    audit_ref(subject, "simulation.risk.decided", "risk_decision", risk.decision_id, correlation, result.decision)
    order.risk_decision_id = risk.decision_id
    if result.decision != "ALLOW":
        order.state = OrderState.REJECTED
        order.save(update_fields=("risk_decision_id", "state", "updated_at"))
        enqueue_event(aggregate_type="order", aggregate_id=order.id, event_type="trading.order.rejected.v1", payload=event_payload(order, reason_codes=list(result.reason_codes)), tenant_ref=tenant, correlation_id=correlation)
        SIMULATED_REJECTIONS.inc()
    else:
        reservation = SimulatedFinancialAdapter().reserve_funds(account=account, order_id=order.id, instrument_id=order.instrument_id, side=order.side, quantity=order.quantity, price=payload["price"])
        order.reservation_id = reservation.id
        order.save(update_fields=("risk_decision_id", "reservation_id", "updated_at"))
        enqueue_event(aggregate_type="order", aggregate_id=order.id, event_type="trading.order.created.v1", payload=event_payload(order), tenant_ref=tenant, correlation_id=correlation)
    audit(user, "simulation.order.submitted", order.id, correlation)
    SIMULATED_ORDERS.labels(decision=result.decision).inc()
    body = serialize_order(order)
    complete_idempotent_request(record, status=201, body=body, resource_type="simulation_order", resource_id=order.id)
    if settings.SIMULATED_EXECUTION_INLINE and result.decision == "ALLOW":
        transaction.on_commit(lambda: process_created_order(order.id))
    return body, 201


@SIMULATION_EXECUTION_LATENCY.time()
@transaction.atomic
def apply_execution(order_id, execution):
    order = TradingOrder.objects.select_for_update().get(pk=order_id, simulation=True)
    envelope = {"event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, execution.execution_id)), "payload": {"execution_id": execution.execution_id, "order_id": str(order.id), "quantity": str(execution.quantity), "price": str(execution.price), "outcome": execution.outcome}}
    def mutation():
        nonlocal order
        enqueue_event(
            aggregate_type="execution",
            aggregate_id=execution.execution_id,
            event_type="trading.execution.received.v1",
            payload=event_payload(order, execution_id=execution.execution_id, outcome=execution.outcome),
            tenant_ref=order.tenant_ref,
        )
        if execution.outcome == "REJECT":
            order.state = transition_order(order.state, "REJECTED")
            SimulatedFinancialAdapter().release_reservation(SimulatedReservation.objects.get(pk=order.reservation_id))
            event_type = "trading.order.rejected.v1"
        elif execution.outcome == "EXPIRE":
            if order.state == "PENDING": order.state = transition_order(order.state, "ACCEPTED")
            if order.state == "ACCEPTED": order.state = transition_order(order.state, "OPEN")
            order.state = transition_order(order.state, "EXPIRED")
            SimulatedFinancialAdapter().release_reservation(SimulatedReservation.objects.get(pk=order.reservation_id))
            event_type = "trading.order.expired.v1"
        else:
            if order.state == "PENDING": order.state = transition_order(order.state, "ACCEPTED")
            if order.state == "ACCEPTED": order.state = transition_order(order.state, "OPEN")
            next_filled = order.filled_quantity + execution.quantity
            if next_filled > order.quantity: raise ValueError("EXECUTION_OVERFILL")
            fee = execution.quantity * execution.price * FEE_RATE
            account, position, _ = SimulatedFinancialAdapter().settle_trade(reservation=SimulatedReservation.objects.get(pk=order.reservation_id), side=order.side, instrument_id=order.instrument_id, quantity=execution.quantity, price=execution.price, fee=fee)
            SimulatedTrade.objects.create(order=order, execution_id=execution.execution_id, instrument_id=order.instrument_id, side=order.side, quantity=execution.quantity, price=execution.price, fee=fee, executed_at=timezone.now())
            SIMULATED_FILLS.inc()
            audit_ref(order.subject_ref, "simulation.execution.received", "simulation_execution", execution.execution_id, uuid.uuid4())
            audit_ref(order.subject_ref, "simulation.trade.executed", "simulation_trade", execution.execution_id, uuid.uuid4())
            audit_ref(order.subject_ref, "simulation.settlement.applied", "simulation_reservation", order.reservation_id, uuid.uuid4())
            previous_value = order.filled_quantity * (order.average_fill_price or Decimal("0"))
            order.filled_quantity = next_filled
            order.average_fill_price = (previous_value + execution.quantity * execution.price) / next_filled
            order.state = transition_order(order.state, "FILLED" if next_filled == order.quantity else "PARTIALLY_FILLED")
            event_type = "trading.order.filled.v1" if order.state == "FILLED" else "trading.order.partially_filled.v1"
            tenant = order.tenant_ref
            enqueue_event(aggregate_type="trade", aggregate_id=execution.execution_id, event_type="trading.trade.executed.v1", payload=event_payload(order, execution_id=execution.execution_id, price=str(execution.price), fee=str(fee)), tenant_ref=tenant)
            enqueue_event(aggregate_type="position", aggregate_id=position.id, event_type="trading.position.updated.v1", payload={"position_id": str(position.id), "account_ref": order.account_ref, "instrument": order.instrument_id, "quantity": str(position.quantity), "average_price": str(position.average_price), "simulation": True}, tenant_ref=tenant)
            enqueue_event(aggregate_type="account", aggregate_id=account.id, event_type="trading.balance_projection.updated.v1", payload=serialize_account(account), tenant_ref=tenant)
        order.save(update_fields=("state", "filled_quantity", "average_fill_price", "updated_at"))
        enqueue_event(aggregate_type="order", aggregate_id=order.id, event_type=event_type, payload=event_payload(order), tenant_ref=order.tenant_ref)
    consumed = consume_once(envelope=envelope, consumer_name="simulated-execution-v1", mutation=mutation)
    if not consumed:
        SIMULATION_DUPLICATE_EVENTS.inc()
    return consumed


@SIMULATION_ORDER_PROCESSING_LATENCY.time()
@transaction.atomic
def process_created_order(order_id, scenario=None):
    order = TradingOrder.objects.get(pk=order_id, simulation=True)
    selected = scenario or settings.SIMULATED_EXECUTION_SCENARIO
    if order.state == "PENDING" and selected != "REJECT":
        order.state = transition_order(order.state, "ACCEPTED"); order.save(update_fields=("state", "updated_at"))
        enqueue_event(aggregate_type="order", aggregate_id=order.id, event_type="trading.order.accepted.v1", payload=event_payload(order), tenant_ref=order.tenant_ref)
    for execution in SimulatedExecutionProvider(selected).submit_order(order):
        apply_execution(order.id, execution)
    order.refresh_from_db()
    if order.state == "ACCEPTED":
        order.state = transition_order(order.state, "OPEN"); order.save(update_fields=("state", "updated_at"))
        enqueue_event(aggregate_type="order", aggregate_id=order.id, event_type="trading.order.opened.v1", payload=event_payload(order), tenant_ref=order.tenant_ref)
    return order


@transaction.atomic
def cancel(user, order_id):
    tenant, subject, _ = refs(user)
    order = TradingOrder.objects.select_for_update().get(pk=order_id, tenant_ref=tenant, subject_ref=subject, simulation=True)
    if order.state not in {"ACCEPTED", "OPEN", "PARTIALLY_FILLED"}: raise ValueError("ORDER_INVALID_STATE")
    order.state = transition_order(order.state, "CANCEL_PENDING")
    order.save(update_fields=("state", "updated_at"))
    enqueue_event(aggregate_type="order", aggregate_id=order.id, event_type="trading.order.cancel_requested.v1", payload=event_payload(order), tenant_ref=tenant)
    order.state = transition_order(order.state, "CANCELLED")
    order.save(update_fields=("state", "updated_at"))
    SimulatedFinancialAdapter().release_reservation(SimulatedReservation.objects.get(pk=order.reservation_id))
    enqueue_event(aggregate_type="order", aggregate_id=order.id, event_type="trading.order.cancelled.v1", payload=event_payload(order), tenant_ref=tenant)
    audit(user, "simulation.order.cancelled", order.id, uuid.uuid4())
    SIMULATED_CANCELLATIONS.inc()
    return serialize_order(order)


def serialize_order(order):
    return {"id": str(order.id), "instrument": order.instrument_id, "side": order.side, "order_type": order.order_type, "quantity": str(order.quantity), "filled_quantity": str(order.filled_quantity), "state": order.state, "simulation": True}


def serialize_account(account):
    reserved = account.reservations.filter(state=SimulatedReservation.State.ACTIVE).aggregate(total=__import__("django.db.models", fromlist=["Sum"]).Sum("remaining_amount"))["total"] or Decimal("0")
    return {"id": str(account.id), "account_ref": account.account_ref, "currency": account.quote_currency, "total": str(account.total_balance), "available": str(SimulatedFinancialAdapter.available_quote(account)), "reserved": str(reserved), "pending": str(account.pending_balance), "simulation": True}
