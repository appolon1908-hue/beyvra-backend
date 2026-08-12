import os

from django.db.models import Sum
from django.utils import timezone

from apps.trading.models import SimulatedReservation, SimulatedTrade

from .common import POLICY_VERSION, audit, publish
from .models import PostTradeAudit, PostTradeReconciliationRun, Trade
from .observability import RECONCILIATION_VIOLATIONS


class PositionReconciler:
    CHECKS = ("FILL_WITHOUT_TRADE", "TRADE_WITHOUT_FILL", "TRADE_WITHOUT_POSITION_EFFECT", "POSITION_WITHOUT_TRADE_BASIS", "QUANTITY_MISMATCH", "SIDE_MISMATCH", "INSTRUMENT_MISMATCH", "ACCOUNT_MISMATCH", "DUPLICATE_POSITION_EFFECT", "RESERVATION_NOT_RELEASED", "SETTLEMENT_OBLIGATION_MISSING", "SETTLEMENT_INSTRUCTION_MISSING", "CONFIRMATION_MISSING", "AUDIT_GAP", "OUTBOX_GAP")

    @classmethod
    def run(cls, *, tenant_ref="default", persist=True):
        started = timezone.now(); violations = []
        trades = Trade.objects.filter(tenant_ref=tenant_ref).select_related("settlement_instruction")
        for trade in trades:
            fill = SimulatedTrade.objects.filter(execution_id=trade.execution_id).first()
            if not fill: violations.append({"check": "TRADE_WITHOUT_FILL", "trade_id": str(trade.id)})
            elif fill.quantity != trade.quantity: violations.append({"check": "QUANTITY_MISMATCH", "trade_id": str(trade.id)})
            if trade.position_effects.filter(effect_type="TRADE").count() != 1: violations.append({"check": "TRADE_WITHOUT_POSITION_EFFECT", "trade_id": str(trade.id)})
            if trade.allocations.aggregate(total=Sum("allocation_quantity"))["total"] != trade.quantity: violations.append({"check": "ALLOCATION_MISMATCH", "trade_id": str(trade.id)})
            if trade.obligations.count() != 3: violations.append({"check": "SETTLEMENT_OBLIGATION_MISSING", "trade_id": str(trade.id)})
            if not hasattr(trade, "settlement_instruction"): violations.append({"check": "SETTLEMENT_INSTRUCTION_MISSING", "trade_id": str(trade.id)})
            if not trade.confirmations.exists(): violations.append({"check": "CONFIRMATION_MISSING", "trade_id": str(trade.id)})
            if not PostTradeAudit.objects.filter(tenant_ref=tenant_ref, resource_ref=str(trade.id)).exists(): violations.append({"check": "AUDIT_GAP", "trade_id": str(trade.id)})
        for fill in SimulatedTrade.objects.filter(order__tenant_ref=tenant_ref):
            if not Trade.objects.filter(execution_id=fill.execution_id).exists(): violations.append({"check": "FILL_WITHOUT_TRADE", "execution_id": fill.execution_id})
        active_for_final = SimulatedReservation.objects.filter(account__tenant_ref=tenant_ref, state="ACTIVE", order_id__in=trades.values("order_id"))
        violations.extend({"check": "RESERVATION_NOT_RELEASED", "reservation_id": str(row.id)} for row in active_for_final)
        status = "PASS" if not violations else "FAIL"
        for violation in violations: RECONCILIATION_VIOLATIONS.labels(violation["check"]).inc()
        result = {"status": status, "checks": {name: sum(v["check"] == name for v in violations) for name in cls.CHECKS}, "violations": violations}
        if persist:
            run = PostTradeReconciliationRun.objects.create(tenant_ref=tenant_ref, started_at=started, completed_at=timezone.now(), status=status, checks=result["checks"], violations=violations, candidate_sha=os.getenv("CANDIDATE_SHA", "local"), policy_version=POLICY_VERSION)
            audit(tenant_ref=tenant_ref, actor_ref="system", action="post_trade.reconciliation.run", resource_type="post_trade_reconciliation", resource_ref=run.id, evidence={"status": status, "violations": violations})
            first = trades.first()
            if first: publish(trade=first, event_type="post_trade.reconciliation.completed.v1", payload={"run_id": str(run.id), "status": status})
            result["run_id"] = str(run.id)
        return result
