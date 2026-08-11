from django.db import transaction
from django.utils import timezone

from .allocation import TradeAllocationService
from .capture import TradeCaptureService
from .confirmations import TradeConfirmationService
from .models import TradePositionEffect
from .obligations import ObligationService
from .settlement import SettlementInstructionService
from .state import PostTradeStateService


@transaction.atomic
def process_simulated_fill(*, order, execution_id, quantity, price, fee, executed_at=None):
    trade, created = TradeCaptureService.capture_fill(order=order, execution_id=execution_id, quantity=quantity, price=price, fee=fee, executed_at=executed_at or timezone.now())
    if not created:
        return trade, False
    PostTradeStateService.transition(trade, "VALIDATING")
    trade = PostTradeStateService.transition(trade, "VALIDATED")
    TradeAllocationService.allocate(trade)
    trade = PostTradeStateService.transition(trade, "ALLOCATED")
    ObligationService.calculate(trade)
    TradePositionEffect.objects.create(trade=trade, account_ref=trade.account_ref, instrument_id=trade.instrument_id, quantity_delta=trade.quantity if trade.side == "BUY" else -trade.quantity, cost_basis_delta=trade.gross_notional if trade.side == "BUY" else -trade.gross_notional, effect_type="TRADE", applied_at=timezone.now(), simulation=True)
    trade = PostTradeStateService.transition(trade, "SETTLEMENT_PENDING")
    instruction, _ = SettlementInstructionService.create_from_trade(trade)
    trade = PostTradeStateService.transition(trade, "SETTLEMENT_INSTRUCTED")
    TradeConfirmationService.generate(trade)
    trade = PostTradeStateService.transition(trade, "SETTLEMENT_PROCESSING")
    trade = PostTradeStateService.transition(trade, "SETTLED")
    instruction.state = "SETTLED"
    instruction.save(update_fields=("state", "updated_at"))
    # Portfolio accounting consumes the canonical trade only after the
    # simulated post-trade chain is complete. It never reads Financial DB.
    from apps.valuation.accounting import process_trade_accounting
    process_trade_accounting(trade)
    return trade, True
