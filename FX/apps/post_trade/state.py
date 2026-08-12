from .common import audit, publish
from .models import Trade


class PostTradeStateService:
    TRANSITIONS = {
        "CAPTURED": {"VALIDATING", "EXCEPTION", "CANCELLED"},
        "VALIDATING": {"VALIDATED", "EXCEPTION", "FAILED"},
        "VALIDATED": {"ALLOCATION_PENDING", "ALLOCATED", "EXCEPTION"},
        "ALLOCATION_PENDING": {"ALLOCATED", "EXCEPTION"},
        "ALLOCATED": {"SETTLEMENT_PENDING", "EXCEPTION"},
        "SETTLEMENT_PENDING": {"SETTLEMENT_INSTRUCTED", "EXCEPTION", "CANCELLED"},
        "SETTLEMENT_INSTRUCTED": {"SETTLEMENT_PROCESSING", "SETTLED", "EXCEPTION", "CANCELLED"},
        "SETTLEMENT_PROCESSING": {"SETTLED", "EXCEPTION", "FAILED"},
        "EXCEPTION": {"VALIDATING", "FAILED", "REVERSED", "CANCELLED"},
        "SETTLED": {"REVERSED"},
    }

    @classmethod
    def can_transition(cls, current, target):
        return target in cls.TRANSITIONS.get(current, set())

    @classmethod
    def explain_transition(cls, current, target):
        return {"allowed": cls.can_transition(current, target), "from": current, "to": target, "reason": "EXPLICIT_TRANSITION_MATRIX"}

    @classmethod
    def transition(cls, trade, target, actor_ref="system"):
        trade = Trade.objects.select_for_update().get(pk=trade.pk)
        if not cls.can_transition(trade.trade_state, target):
            raise ValueError("INVALID_POST_TRADE_TRANSITION")
        previous = trade.trade_state
        trade.trade_state = target
        trade.version += 1
        trade.save(update_fields=("trade_state", "version", "updated_at"))
        audit(tenant_ref=trade.tenant_ref, actor_ref=actor_ref, action="post_trade.state.changed", resource_type="trade", resource_ref=trade.id, evidence={"from": previous, "to": target, "version": trade.version})
        publish(trade=trade, event_type="trade.validated.v1" if target == "VALIDATED" else "post_trade.settlement.updated.v1", payload={"state": target, "version": trade.version})
        return trade
