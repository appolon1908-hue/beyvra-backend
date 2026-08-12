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

def evaluate(snapshot):
    orders = snapshot.get("orders", [])
    trades = snapshot.get("trades", [])
    reservations = snapshot.get("reservations", [])
    outbox = snapshot.get("outbox", [])
    audits = snapshot.get("audit_events", [])
    counts = {name: 0 for name in INVARIANTS}
    counts["DUPLICATE_ORDERS"] = len(orders) - len({o["id"] for o in orders})
    counts["DUPLICATE_TRADES"] = len(trades) - len({t["execution_id"] for t in trades})
    counts["DUPLICATE_SETTLEMENTS"] = max(0, len(snapshot.get("settlements", [])) - len({s["execution_id"] for s in snapshot.get("settlements", [])}))
    counts["OVERFILLED_ORDERS"] = sum(Decimal(str(o.get("filled_quantity", 0))) > Decimal(str(o["quantity"])) for o in orders)
    counts["NEGATIVE_AVAILABLE_BALANCES"] = sum(Decimal(str(a.get("available", 0))) < 0 for a in snapshot.get("wallets", []))
    counts["NEGATIVE_RESERVED_BALANCES"] = sum(Decimal(str(a.get("reserved", 0))) < 0 for a in snapshot.get("wallets", []))
    order_ids = {str(o["id"]) for o in orders}
    counts["LOST_COMMITTED_OUTBOX_EVENTS"] = sum(str(o["id"]) not in {str(e.get("aggregate_id")) for e in outbox} for o in orders)
    counts["MISSING_REQUIRED_AUDIT_EVENTS"] = sum(str(o["id"]) not in {str(a.get("resource_id")) for a in audits} for o in orders)
    terminal = {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
    counts["RESERVATION_LEAKS"] = sum(str(r.get("order_id")) in order_ids and r.get("order_state") in terminal and r.get("state") == "ACTIVE" for r in reservations)
    counts["INVALID_ORDER_STATES"] = sum(o.get("state") not in {"PENDING","ACCEPTED","OPEN","PARTIALLY_FILLED","FILLED","CANCELLED","REJECTED","EXPIRED"} for o in orders)
    return [Finding(name, int(counts[name])) for name in INVARIANTS]

def assert_all(snapshot):
    findings = evaluate(snapshot)
    failures = [f for f in findings if f.count]
    if failures:
        raise AssertionError(", ".join(f"{f.invariant}={f.count}" for f in failures))
    return findings
