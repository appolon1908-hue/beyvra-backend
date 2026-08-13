from django.utils import timezone

from .common import audit, publish
from .models import TradeConfirmation
from .observability import CONFIRMATIONS


class TradeConfirmationService:
    @classmethod
    def generate(cls, trade):
        fee = trade.fee_snapshot.total_fee
        net = trade.gross_notional + fee if trade.side == "BUY" else trade.gross_notional - fee
        confirmation, created = TradeConfirmation.objects.get_or_create(trade=trade, version=1, defaults={"account_ref": trade.account_ref, "confirmation_number": f"SIM-{str(trade.id).replace('-', '').upper()[:20]}", "trade_date": trade.trade_time.date(), "settlement_date": trade.settlement_date, "instrument_snapshot": {"instrument_id": trade.instrument_id, "display_symbol": trade.instrument_id, "source": "canonical_instrument_authority"}, "side": trade.side, "quantity": trade.quantity, "price": trade.price, "gross_notional": trade.gross_notional, "fees": fee, "net_amount": net, "currency": trade.trade_currency, "venue_safe": trade.venue_id, "execution_mode": trade.execution_mode, "generated_at": timezone.now()})
        if created:
            audit(tenant_ref=trade.tenant_ref, actor_ref="system", action="trade.confirmation.generated", resource_type="trade_confirmation", resource_ref=confirmation.id, evidence={"trade_id": str(trade.id), "version": 1})
            publish(trade=trade, event_type="post_trade.confirmation.generated.v1", payload={"confirmation_id": str(confirmation.id), "version": 1})
            CONFIRMATIONS.labels("simulation").inc()
        return confirmation, created
