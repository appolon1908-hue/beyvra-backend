import json
from django.core.management.base import BaseCommand
from apps.foundation.models import ApplicationAuditEvent, OutboxEvent, ProcessedEvent
from apps.trading.models import SimulatedAccount, SimulatedPosition, SimulatedReservation, SimulatedTrade, TradingOrder
from chaos.invariants import evaluate

class Command(BaseCommand):
    help = "Read-only reconciliation of simulated trading projections and event ledgers"
    def add_arguments(self, parser):
        parser.add_argument("--format", choices=("human", "json"), default="human")
        parser.add_argument("--tenant")
    def handle(self, *args, **options):
        orders = TradingOrder.objects.filter(simulation=True)
        if options["tenant"]: orders = orders.filter(tenant_ref=options["tenant"])
        ids = [str(x) for x in orders.values_list("id", flat=True)]
        snapshot = {
            "orders": list(orders.values("id", "quantity", "filled_quantity", "state")),
            "trades": list(SimulatedTrade.objects.filter(order_id__in=ids).values("execution_id", "quantity")),
            "reservations": [{**r, "order_state": next((o["state"] for o in orders.values("id","state") if str(o["id"]) == str(r["order_id"])), None)} for r in SimulatedReservation.objects.filter(order_id__in=ids).values("order_id","state")],
            "wallets": [{"available": a.total_balance-a.pending_balance, "reserved": a.pending_balance} for a in SimulatedAccount.objects.all()],
            "positions": list(SimulatedPosition.objects.values("instrument_id","quantity","average_price")),
            "outbox": list(OutboxEvent.objects.filter(aggregate_id__in=ids).values("aggregate_id","event_id","state")),
            "processed_events": list(ProcessedEvent.objects.values("event_id","consumer_name")),
            "audit_events": list(ApplicationAuditEvent.objects.filter(resource_id__in=ids).values("resource_id","action")),
            "settlements": list(SimulatedTrade.objects.filter(order_id__in=ids).values("execution_id")),
        }
        findings = evaluate(snapshot); passed = not any(x.count for x in findings)
        report = {"reconciliation": "PASS" if passed else "FAIL", "read_only": True, "counts": {k: len(v) for k,v in snapshot.items()}, "invariants": {x.invariant: x.count for x in findings}}
        if options["format"] == "json": self.stdout.write(json.dumps(report, sort_keys=True))
        else:
            self.stdout.write(f"RECONCILIATION={report['reconciliation']}")
            for key,value in report["invariants"].items(): self.stdout.write(f"{key}={value}")
        if not passed: raise SystemExit(1)
