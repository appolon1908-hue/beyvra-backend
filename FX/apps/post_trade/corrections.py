from django.db import transaction
from django.utils import timezone

from .common import audit
from .models import TradeConfirmation, TradeCorrection, TradePositionEffect


class TradeCorrectionService:
    @staticmethod
    def request(*, trade, correction_type, reason_code, actor_ref):
        return TradeCorrection.objects.create(original_trade=trade, correction_type=correction_type, reason_code=reason_code, requested_by=actor_ref)

    @staticmethod
    @transaction.atomic
    def approve(correction, *, actor_ref):
        correction = TradeCorrection.objects.select_for_update().select_related("original_trade").get(pk=correction.pk)
        if correction.requested_by == actor_ref:
            raise ValueError("SELF_APPROVAL_FORBIDDEN")
        if correction.status != "PENDING":
            raise ValueError("CORRECTION_INVALID_STATE")
        trade = correction.original_trade
        delta = -trade.quantity if trade.side == "BUY" else trade.quantity
        TradePositionEffect.objects.create(trade=trade, account_ref=trade.account_ref, instrument_id=trade.instrument_id, quantity_delta=delta, cost_basis_delta=-(trade.gross_notional), effect_type=correction.correction_type, applied_at=timezone.now(), simulation=True)
        correction.status = "APPROVED"; correction.approved_by = actor_ref; correction.approved_at = timezone.now(); correction.save(update_fields=("status", "approved_by", "approved_at"))
        trade.trade_state = "REVERSED"; trade.version += 1; trade.save(update_fields=("trade_state", "version", "updated_at"))
        confirmation = trade.confirmations.order_by("-version").first()
        if confirmation:
            TradeConfirmation.objects.create(trade=trade, account_ref=confirmation.account_ref, confirmation_number=f"{confirmation.confirmation_number}-R{confirmation.version + 1}", version=confirmation.version + 1, trade_date=confirmation.trade_date, settlement_date=confirmation.settlement_date, instrument_snapshot=confirmation.instrument_snapshot, side=confirmation.side, quantity=confirmation.quantity, price=confirmation.price, gross_notional=confirmation.gross_notional, fees=confirmation.fees, net_amount=-confirmation.net_amount, currency=confirmation.currency, venue_safe=confirmation.venue_safe, execution_mode=confirmation.execution_mode, generated_at=timezone.now(), supersedes=confirmation, status="REVERSED")
        audit(tenant_ref=trade.tenant_ref, actor_ref=actor_ref, action="trade.reversed", resource_type="trade", resource_ref=trade.id, evidence={"correction_id": str(correction.id), "type": correction.correction_type})
        return correction
