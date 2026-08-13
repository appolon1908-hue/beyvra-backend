from .cost_basis import CostBasisService
from .lots import TaxLotService
from .models import PortfolioIncomeExpenseEvent
from .common import POLICY_VERSION


def process_trade_accounting(trade):
    if trade.side == "BUY":
        TaxLotService.open_for_trade(trade)
    else:
        TaxLotService.dispose_fifo(trade)
    fee = trade.fee_snapshot.total_fee
    if fee:
        PortfolioIncomeExpenseEvent.objects.get_or_create(event_type="COMMISSION", source_ref=str(trade.id), defaults={"tenant_ref": trade.tenant_ref, "account_ref": trade.account_ref, "instrument_id": trade.instrument_id, "amount": -fee, "currency": trade.trade_currency, "effective_at": trade.trade_time, "policy_version": POLICY_VERSION, "simulation": True})
    CostBasisService.calculate(tenant_ref=trade.tenant_ref, account_ref=trade.account_ref, instrument_id=trade.instrument_id)
