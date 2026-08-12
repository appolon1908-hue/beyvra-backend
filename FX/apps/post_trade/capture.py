import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .calendar import SettlementCalendarService
from .common import POLICY_VERSION, audit, publish
from .models import FeeSnapshot, Trade
from .observability import TRADES_CAPTURED


class TradeCaptureService:
    @classmethod
    @transaction.atomic
    def capture_fill(cls, *, order, execution_id, quantity, price, fee, executed_at, source_event_id=None):
        quantity, price, fee = Decimal(quantity), Decimal(price), Decimal(fee)
        if quantity <= 0 or price <= 0:
            raise ValueError("INVALID_FILL")
        if order.tenant_ref != "default" or not order.simulation:
            raise ValueError("TRADE_SCOPE_INVALID")
        source_event_id = source_event_id or uuid.uuid5(uuid.NAMESPACE_URL, f"post-trade:{execution_id}")
        settlement_date, _policy = SettlementCalendarService.calculate_settlement_date(trade_date=executed_at.date(), asset_class="CRYPTO")
        trade, created = Trade.objects.get_or_create(execution_id=execution_id, defaults={"tenant_ref": order.tenant_ref, "account_ref": order.account_ref, "order_id": order.id, "instrument_id": order.instrument_id, "side": order.side, "quantity": quantity, "price": price, "gross_notional": quantity * price, "trade_currency": "USD", "execution_provider_id": "simulation", "venue_id": "SIMULATED", "execution_mode": "SIMULATION", "trade_time": executed_at, "captured_at": timezone.now(), "settlement_date": settlement_date, "source_event_id": source_event_id, "simulation": True})
        if not created:
            return trade, False
        FeeSnapshot.objects.create(trade=trade, total_fee=fee, commission=fee, currency="USD", pricing_policy_version="simulation-fee-v1")
        audit(tenant_ref=trade.tenant_ref, actor_ref="system", action="trade.captured", resource_type="trade", resource_ref=trade.id, evidence={"execution_id": execution_id, "quantity": str(quantity), "price": str(price), "source_event_id": str(source_event_id)})
        publish(trade=trade, event_type="trading.trade.captured.v1", payload={"state": trade.trade_state, "instrument_id": trade.instrument_id, "quantity": str(quantity)})
        transaction.on_commit(lambda: TRADES_CAPTURED.labels("simulation", "created").inc())
        return trade, created

    capture_execution = capture_fill

    @staticmethod
    def get_trade(trade_id, *, tenant_ref, account_ref=None):
        rows = Trade.objects.filter(pk=trade_id, tenant_ref=tenant_ref)
        return rows.filter(account_ref=account_ref).first() if account_ref else rows.first()

    @staticmethod
    def list_trades(*, tenant_ref, account_ref=None):
        rows = Trade.objects.filter(tenant_ref=tenant_ref).order_by("-trade_time", "-id")
        return rows.filter(account_ref=account_ref) if account_ref else rows
