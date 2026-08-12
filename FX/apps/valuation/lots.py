from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .common import LOT_POLICY, POLICY_VERSION, audit
from .models import RealizedPnLEvent, TaxLot, TaxLotDisposition


class TaxLotService:
    @staticmethod
    def open_for_trade(trade):
        if trade.side != "BUY":
            raise ValueError("ACQUISITION_TRADE_REQUIRED")
        fee = trade.fee_snapshot.total_fee
        total = trade.gross_notional + fee
        lot, created = TaxLot.objects.get_or_create(acquisition_trade=trade, defaults={"tenant_ref": trade.tenant_ref, "account_ref": trade.account_ref, "instrument_id": trade.instrument_id, "acquisition_date": trade.trade_time.date(), "original_quantity": trade.quantity, "remaining_quantity": trade.quantity, "unit_cost": total / trade.quantity, "total_cost": total, "currency": trade.trade_currency, "source_type": "TRADE", "status": "OPEN", "policy_version": POLICY_VERSION})
        if created:
            audit(tenant_ref=trade.tenant_ref, action="valuation.tax_lot.opened", resource=lot, evidence={"trade": str(trade.id), "policy": LOT_POLICY})
        return lot, created

    @classmethod
    @transaction.atomic
    def dispose_fifo(cls, trade):
        existing = RealizedPnLEvent.objects.filter(disposal_trade=trade).first()
        if existing:
            return existing, False
        needed = trade.quantity
        lots = list(TaxLot.objects.select_for_update().filter(tenant_ref=trade.tenant_ref, account_ref=trade.account_ref, instrument_id=trade.instrument_id, remaining_quantity__gt=0).order_by("acquisition_date", "created_at", "id"))
        if sum((lot.remaining_quantity for lot in lots), Decimal("0")) < needed:
            raise ValueError("TAX_LOT_INSUFFICIENT_QUANTITY")
        allocated_basis = Decimal("0")
        for lot in lots:
            if needed <= 0:
                break
            quantity = min(needed, lot.remaining_quantity)
            basis = quantity * lot.unit_cost
            proceeds = trade.gross_notional * quantity / trade.quantity
            TaxLotDisposition.objects.create(lot=lot, disposal_trade=trade, quantity=quantity, allocated_basis=basis, proceeds=proceeds, realized_gain_loss=proceeds - basis, disposed_at=trade.trade_time, selection_method=LOT_POLICY, policy_version=POLICY_VERSION)
            lot.remaining_quantity -= quantity
            lot.status = "CLOSED" if lot.remaining_quantity == 0 else "PARTIALLY_DISPOSED"
            lot.save(update_fields=("remaining_quantity", "status"))
            allocated_basis += basis
            needed -= quantity
        fee = trade.fee_snapshot.total_fee
        event = RealizedPnLEvent.objects.create(tenant_ref=trade.tenant_ref, account_ref=trade.account_ref, instrument_id=trade.instrument_id, disposal_trade=trade, quantity=trade.quantity, proceeds=trade.gross_notional, allocated_cost_basis=allocated_basis, fees=fee, realized_pnl=trade.gross_notional - allocated_basis - fee, currency=trade.trade_currency, base_currency_pnl=trade.gross_notional - allocated_basis - fee, lot_method=LOT_POLICY, policy_version=POLICY_VERSION, realized_at=trade.trade_time, simulation=True)
        audit(tenant_ref=trade.tenant_ref, action="valuation.realized_pnl.generated", resource=event, evidence={"trade": str(trade.id), "basis": str(allocated_basis), "policy": LOT_POLICY})
        return event, True

