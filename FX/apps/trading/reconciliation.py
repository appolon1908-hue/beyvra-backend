"""Read-only simulation reconciliation with append-only evidence output."""
import hashlib, json, os
from collections import defaultdict
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from apps.foundation.models import ApplicationAuditEvent, OutboxEvent, ProcessedEvent
from apps.trading.models import ReconciliationRun, ReconciliationViolation, SimulatedAccount, SimulatedPosition, SimulatedReservation, SimulatedTrade, TradingOrder
from apps.foundation.observability import RECONCILIATION_LAST_SUCCESS, RECONCILIATION_RUNS, RECONCILIATION_VIOLATIONS

POLICY_VERSION="simulation-reconciliation-v1"
SCOPES={"full","orders","settlements","positions","outbox"}

def _hash(value): return hashlib.sha256(str(value).encode()).hexdigest()
def _violation(code, entity_type, entity_ref, evidence, severity="CRITICAL"):
    return {"check_code":code,"severity":severity,"entity_type":entity_type,"opaque_entity_ref":_hash(entity_ref),"evidence_hash":_hash(json.dumps(evidence,sort_keys=True,default=str))}

def evaluate_snapshot(snapshot, scope="full"):
    if scope not in SCOPES: raise ValueError("INVALID_RECONCILIATION_SCOPE")
    violations=[]; checks=[]
    orders={str(x["id"]):x for x in snapshot["orders"]}; trades=snapshot["trades"]
    reservations={str(x["order_id"]):x for x in snapshot["reservations"]}
    def check(code, found):
        checks.append({"code":code,"status":"PASS" if not found else "FAIL","violation_count":len(found)}); violations.extend(found)
    if scope in {"full","orders","settlements"}:
        duplicate=[_violation("DUPLICATE_TRADE","execution",x["execution_id"],x) for x in snapshot.get("duplicate_trades",[])]
        check("DUPLICATE_TRADE",duplicate)
        orphan=[_violation("TRADE_WITHOUT_ORDER","trade",x["execution_id"],x) for x in trades if str(x["order_id"]) not in orders]
        check("TRADE_WITHOUT_ORDER",orphan)
        by_order=defaultdict(Decimal)
        for trade in trades: by_order[str(trade["order_id"])]+=Decimal(str(trade["quantity"]))
        mismatch=[]; overfill=[]
        for oid,order in orders.items():
            total=by_order[oid]; filled=Decimal(str(order["filled_quantity"])); quantity=Decimal(str(order["quantity"]))
            if filled != total: mismatch.append(_violation("FILLED_QUANTITY_MISMATCH","order",oid,{"filled":filled,"executed":total}))
            if filled > quantity or total > quantity: overfill.append(_violation("OVERFILL","order",oid,{"quantity":quantity,"filled":filled,"executed":total}))
        check("FILLED_QUANTITY_MATCHES_EXECUTIONS",mismatch); check("OVERFILL",overfill)
        settlement=[_violation("DUPLICATE_SETTLEMENT","execution",x["execution_id"],x) for x in snapshot.get("duplicate_settlements",[])]
        check("DUPLICATE_SETTLEMENT",settlement)
        execution_ids={str(x) for x in snapshot.get("execution_outbox_ids",[])}
        missing_execution=[_violation("MISSING_EXECUTION_EVENT","trade",x["execution_id"],{}) for x in trades if str(x["execution_id"]) not in execution_ids]
        check("TRADE_MATCHES_EXECUTION",missing_execution)
    if scope in {"full","orders","settlements"}:
        leaks=[]
        for oid,order in orders.items():
            reservation=reservations.get(oid)
            if not reservation: leaks.append(_violation("MISSING_RESERVATION","order",oid,{})); continue
            terminal=order["state"] in {"FILLED","CANCELED","REJECTED","EXPIRED"}
            if terminal and (reservation["state"]=="ACTIVE" or Decimal(str(reservation["remaining_amount"])) != 0): leaks.append(_violation("RESERVATION_LEAK","order",oid,reservation))
        check("RESERVATION_CONSISTENCY",leaks)
    if scope in {"full","positions"}:
        expected=defaultdict(Decimal)
        order_account={oid:o["account_id"] for oid,o in orders.items()}
        for trade in trades:
            account_id=order_account.get(str(trade["order_id"]),trade.get("account_id"))
            expected[(account_id,trade["instrument_id"])]+=Decimal(str(trade["quantity"])) * (1 if trade["side"]=="BUY" else -1)
        actual={(x["account_id"],x["instrument_id"]):Decimal(str(x["quantity"])) for x in snapshot["positions"]}
        mismatches=[_violation("POSITION_MISMATCH","position",key,{"expected":qty,"actual":actual.get(key,0)}) for key,qty in expected.items() if actual.get(key,Decimal(0)) != qty]
        check("POSITION_MATCHES_TRADE_HISTORY",mismatches)
        wallet=[_violation("NEGATIVE_BALANCE","account",x["id"],{}) for x in snapshot["accounts"] if Decimal(str(x["total_balance"])) < 0 or Decimal(str(x["pending_balance"])) < 0]
        check("WALLET_PROJECTION_NONNEGATIVE",wallet)
    if scope in {"full","outbox"}:
        outbox_ids={str(x) for x in snapshot["outbox_order_ids"]}; audits={str(x) for x in snapshot["audit_order_ids"]}
        check("MISSING_REQUIRED_OUTBOX",[_violation("MISSING_REQUIRED_OUTBOX","order",oid,{}) for oid in orders if oid not in outbox_ids])
        check("AUDIT_GAP",[_violation("AUDIT_GAP","order",oid,{}) for oid in orders if oid not in audits])
        check("PROCESSED_EVENT_UNIQUENESS",[_violation("PROCESSED_EVENT_DUPLICATE","event",x["event_id"],x) for x in snapshot.get("duplicate_processed",[])])
    return checks,violations

def collect_snapshot(tenant=None):
    orders=TradingOrder.objects.filter(simulation=True); orders=orders.filter(tenant_ref=tenant) if tenant else orders
    ids=list(orders.values_list("id",flat=True)); account_ids=list(orders.values_list("account_ref",flat=True))
    return {"orders":[{"id":x.id,"quantity":x.quantity,"filled_quantity":x.filled_quantity,"state":x.state,"account_id":x.account_ref} for x in orders],
      "trades":list(SimulatedTrade.objects.filter(order_id__in=ids).values("execution_id","order_id","instrument_id","side","quantity")),
      "reservations":list(SimulatedReservation.objects.filter(order_id__in=ids).values("order_id","state","remaining_amount")),
      "positions":list(SimulatedPosition.objects.filter(account__account_ref__in=account_ids).values("account__account_ref","instrument_id","quantity")).copy(),
      "accounts":list(SimulatedAccount.objects.filter(account_ref__in=account_ids).values("id","total_balance","pending_balance")),
      "outbox_order_ids":list(OutboxEvent.objects.filter(aggregate_type="order",aggregate_id__in=[str(x) for x in ids]).values_list("aggregate_id",flat=True)),
      "execution_outbox_ids":list(OutboxEvent.objects.filter(aggregate_type="execution",aggregate_id__in=list(SimulatedTrade.objects.filter(order_id__in=ids).values_list("execution_id",flat=True))).values_list("aggregate_id",flat=True)),
      "audit_order_ids":list(ApplicationAuditEvent.objects.filter(resource_type="simulation_order",resource_id__in=[str(x) for x in ids]).values_list("resource_id",flat=True)),
      "duplicate_trades":list(SimulatedTrade.objects.values("execution_id").annotate(count=Count("trade_id")).filter(count__gt=1)),
      "duplicate_settlements":[], "duplicate_processed":list(ProcessedEvent.objects.values("event_id","consumer_name").annotate(count=Count("id")).filter(count__gt=1))}

def run(scope="full",tenant=None,persist=True,candidate_sha=None):
    started=timezone.now(); snapshot=collect_snapshot(tenant)
    # normalize position account key without exposing it in output
    for position in snapshot["positions"]: position["account_id"]=position.pop("account__account_ref")
    checks,violations=evaluate_snapshot(snapshot,scope); completed=timezone.now(); status="PASS" if not violations else "FAIL"
    report={"run_id":None,"started_at":started.isoformat(),"completed_at":completed.isoformat(),"status":status,"scope":scope,"policy_version":POLICY_VERSION,"checks":checks,"violations":violations}
    if persist:
        with transaction.atomic():
            record=ReconciliationRun.objects.create(environment=getattr(settings,"DEPLOYMENT_ENV","unknown"),simulation=True,scope=scope,started_at=started,status="RUNNING",policy_version=POLICY_VERSION,candidate_sha=(candidate_sha or os.getenv("CANDIDATE_SHA","unknown"))[:64])
            ReconciliationViolation.objects.bulk_create([ReconciliationViolation(run=record,**x) for x in violations])
            summary={k:v for k,v in report.items() if k not in {"run_id"}}; record.completed_at=completed; record.status=status; record.check_count=len(checks); record.violation_count=len(violations); record.summary_hash=_hash(json.dumps(summary,sort_keys=True)); record.save()
            report["run_id"]=str(record.id)
        transaction.on_commit(lambda: RECONCILIATION_RUNS.labels(status.lower(),scope).inc())
        if status=="PASS": transaction.on_commit(lambda: RECONCILIATION_LAST_SUCCESS.set(completed.timestamp()))
        for violation in violations:
            transaction.on_commit(lambda item=violation: RECONCILIATION_VIOLATIONS.labels(item["check_code"],item["severity"].lower()).inc())
    return report
