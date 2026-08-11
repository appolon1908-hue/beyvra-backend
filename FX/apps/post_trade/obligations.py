from decimal import Decimal

from django.db import transaction

from .common import POLICY_VERSION, audit
from .models import SettlementObligation


class ObligationService:
    @classmethod
    @transaction.atomic
    def calculate(cls, trade):
        fee = trade.fee_snapshot.total_fee
        base_asset = trade.instrument_id.split("-")[0]
        cash_type, asset_type = (("CASH_DEBIT", "ASSET_RECEIPT") if trade.side == "BUY" else ("CASH_CREDIT", "ASSET_DELIVERY"))
        cash_direction, asset_direction = (("DEBIT", "CREDIT") if trade.side == "BUY" else ("CREDIT", "DEBIT"))
        values = [
            (cash_type, trade.trade_currency, Decimal("0"), trade.gross_notional, cash_direction),
            (asset_type, base_asset, trade.quantity, Decimal("0"), asset_direction),
            ("FEE_DEBIT", trade.trade_currency, Decimal("0"), fee, "DEBIT"),
        ]
        rows = [SettlementObligation.objects.get_or_create(trade=trade, obligation_type=kind, defaults={"account_ref": trade.account_ref, "asset": asset, "quantity": quantity, "currency": trade.trade_currency, "amount": amount, "direction": direction, "due_date": trade.settlement_date, "calculation_policy_version": POLICY_VERSION})[0] for kind, asset, quantity, amount, direction in values]
        cls.validate(trade)
        audit(tenant_ref=trade.tenant_ref, actor_ref="system", action="settlement.obligations.created", resource_type="trade", resource_ref=trade.id, evidence={"obligation_ids": [str(row.id) for row in rows]})
        return rows

    @staticmethod
    def validate(trade):
        if trade.obligations.count() != 3 or any(row.amount < 0 or row.quantity < 0 for row in trade.obligations.all()):
            raise ValueError("SETTLEMENT_OBLIGATION_INVALID")
        return True

    @staticmethod
    def list_for_trade(trade):
        return trade.obligations.order_by("obligation_type")
