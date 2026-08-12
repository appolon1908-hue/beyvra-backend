"""Reusable, side-effect-free trading invariant checks."""
from dataclasses import dataclass
from decimal import Decimal

INVARIANTS = (
    "LOST_COMMITTED_ORDERS", "LOST_COMMITTED_OUTBOX_EVENTS", "DUPLICATE_ORDERS",
    "DUPLICATE_TRADES", "DUPLICATE_SETTLEMENTS", "OVERFILLED_ORDERS",
    "RESERVATION_LEAKS", "NEGATIVE_AVAILABLE_BALANCES", "NEGATIVE_RESERVED_BALANCES",
    "POSITION_ACCOUNTING_ERRORS", "CROSS_TENANT_ACCESS_SUCCESSES",
    "INVALID_ORDER_STATES", "MISSING_REQUIRED_AUDIT_EVENTS",
)

@dataclass(frozen=True)
class Finding:
    invariant: str
    count: int
    details: tuple = ()


def _duplicates(values):
    values = [value for value in values if value not in (None, "")]
    return len(values) - len(set(values))


def _decimal(value):
    return Decimal(str(value or 0))


def _position_key(position):
    return (
        str(position.get("tenant_id", position.get("account_id", ""))),
        str(position.get("instrument_id", position.get("symbol", ""))),
    )


def _position_quantity(position):
    return _decimal(position.get("quantity", position.get("net_quantity", 0)))

def evaluate(snapshot):
    orders = snapshot.get("orders", [])
    trades = snapshot.get("trades", [])
    reservations = snapshot.get("reservations", [])
    outbox = snapshot.get("outbox", [])
    audits = snapshot.get("audit_events", [])
    counts = {name: 0 for name in INVARIANTS}
    order_ids = [str(o.get("id")) for o in orders if o.get("id") is not None]
    idempotency_keys = [
        (str(o.get("tenant_id", o.get("account_id", ""))), str(o["idempotency_key"]))
        for o in orders if o.get("idempotency_key") not in (None, "")
    ]
    counts["DUPLICATE_ORDERS"] = _duplicates(order_ids) + _duplicates(idempotency_keys)
    counts["DUPLICATE_TRADES"] = _duplicates(t.get("id") for t in trades) + _duplicates(t.get("execution_id") for t in trades)
    settlements = snapshot.get("settlements", [])
    counts["DUPLICATE_SETTLEMENTS"] = _duplicates(s.get("id") for s in settlements) + _duplicates(
        s.get("execution_id", s.get("trade_id")) for s in settlements
    )
    counts["OVERFILLED_ORDERS"] = sum(_decimal(o.get("filled_quantity")) > _decimal(o.get("quantity")) for o in orders)
    counts["NEGATIVE_AVAILABLE_BALANCES"] = sum(_decimal(a.get("available")) < 0 for a in snapshot.get("wallets", []))
    counts["NEGATIVE_RESERVED_BALANCES"] = sum(_decimal(a.get("reserved")) < 0 for a in snapshot.get("wallets", []))
    order_id_set = set(order_ids)
    committed_order_ids = {str(value) for value in snapshot.get("committed_order_ids", [])}
    counts["LOST_COMMITTED_ORDERS"] = len(committed_order_ids - order_id_set)
    outbox_ids = {str(event.get("id")) for event in outbox if event.get("id") is not None}
    committed_outbox_ids = {str(value) for value in snapshot.get("committed_outbox_event_ids", [])}
    missing_committed_outbox = len(committed_outbox_ids - outbox_ids)
    outbox_aggregate_ids = {str(event.get("aggregate_id")) for event in outbox if event.get("aggregate_id") is not None}
    missing_order_outbox = sum(order_id not in outbox_aggregate_ids for order_id in order_id_set)
    counts["LOST_COMMITTED_OUTBOX_EVENTS"] = missing_committed_outbox + missing_order_outbox
    audit_resource_ids = {str(event.get("resource_id")) for event in audits if event.get("resource_id") is not None}
    counts["MISSING_REQUIRED_AUDIT_EVENTS"] = sum(order_id not in audit_resource_ids for order_id in order_id_set)
    terminal = {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
    counts["RESERVATION_LEAKS"] = sum(str(r.get("order_id")) in order_id_set and r.get("order_state") in terminal and r.get("state") == "ACTIVE" for r in reservations)
    actual_positions = {_position_key(position): _position_quantity(position) for position in snapshot.get("positions", [])}
    expected_positions = {_position_key(position): _position_quantity(position) for position in snapshot.get("expected_positions", [])}
    counts["POSITION_ACCOUNTING_ERRORS"] = sum(
        actual_positions.get(key, Decimal("0")) != expected_positions.get(key, Decimal("0"))
        for key in actual_positions.keys() | expected_positions.keys()
    )
    cross_tenant = snapshot.get("cross_tenant_access_successes", 0)
    counts["CROSS_TENANT_ACCESS_SUCCESSES"] = cross_tenant if isinstance(cross_tenant, int) else len(cross_tenant)
    counts["INVALID_ORDER_STATES"] = sum(o.get("state") not in {"PENDING","ACCEPTED","OPEN","PARTIALLY_FILLED","FILLED","CANCELLED","REJECTED","EXPIRED"} for o in orders)
    return [Finding(name, int(counts[name])) for name in INVARIANTS]

def assert_all(snapshot):
    findings = evaluate(snapshot)
    failures = [f for f in findings if f.count]
    if failures:
        raise AssertionError(", ".join(f"{f.invariant}={f.count}" for f in failures))
    return findings
