from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from wallet.constants import DEMO_WALLET_NAME
from wallet.models import Wallet, Transaction
from .market_data import MarketDataError, get_market_history
from .models import Asset, AssetType, DemoLedgerEntry, Trade, TradeCategory

ALLOWED_DURATIONS = {5, 15, 30, 60}
PAYOUT_RATE = Decimal("0.80")


def quote(symbol):
    rows = get_market_history(symbol=symbol, interval="1m", limit=1)
    if not rows:
        raise MarketDataError("QUOTE_UNAVAILABLE")
    candle = rows[-1]
    return Decimal(str(candle["close"])), timezone.now()


def settle_due_orders():
    now = timezone.now()
    count = 0
    for trade_id in Trade.objects.filter(demo_state="OPEN", expires_at__lte=now).values_list("id", flat=True):
        with transaction.atomic():
            trade = Trade.objects.select_for_update().select_related("wallet", "asset").get(pk=trade_id)
            if trade.demo_state != "OPEN":
                continue
            try:
                closing, _ = quote(trade.asset.symbol)
            except MarketDataError:
                continue
            opening = Decimal(trade.opening_price)
            if closing == opening:
                result, payout = "DRAW", trade.quantity * trade.price_per_unit
            elif (trade.trade_type == "up" and closing > opening) or (trade.trade_type == "down" and closing < opening):
                result, payout = "WON", trade.quantity * trade.price_per_unit * (Decimal("1") + PAYOUT_RATE)
            else:
                result, payout = "LOST", Decimal("0")
            wallet = Wallet.objects.select_for_update().get(pk=trade.wallet_id)
            wallet.balance += payout
            wallet.save(update_fields=["balance", "updated_at"])
            trade.closing_price = closing
            trade.close = closing
            trade.demo_result = result
            trade.demo_state = result
            trade.payout = payout
            trade.net = payout - (trade.quantity * trade.price_per_unit)
            trade.is_active = False
            trade.save(update_fields=["closing_price", "close", "demo_result", "demo_state", "payout", "net", "is_active", "updated_at"])
            DemoLedgerEntry.objects.get_or_create(wallet=wallet, trade=trade, entry_type="SETTLEMENT", idempotency_key=f"settlement:{trade.pk}", defaults={"amount": payout, "description": f"Demo trade {result}"})
            count += 1
    return count


class DemoOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not getattr(settings, "PAPER_TRADING_ONLY", True):
            return Response({"code": "DEMO_ONLY_DISABLED"}, status=503)
        key = request.headers.get("Idempotency-Key", "").strip()
        if not key:
            return Response({"code": "IDEMPOTENCY_KEY_REQUIRED"}, status=400)
        symbol = str(request.data.get("symbol", "BTCUSDT")).upper()
        direction = str(request.data.get("direction", "")).lower()
        try:
            amount = Decimal(str(request.data.get("amount")))
            duration = int(request.data.get("duration"))
        except (TypeError, ValueError, ArithmeticError):
            return Response({"code": "ORDER_INVALID", "message": "Amount and duration are invalid."}, status=400)
        if direction not in {"up", "down"} or amount <= 0 or duration not in ALLOWED_DURATIONS:
            return Response({"code": "ORDER_INVALID", "message": "This demo order is not permitted."}, status=400)
        existing = Trade.objects.filter(idempotency_key=f"demo:{request.user.pk}:{key}").first()
        if existing:
            return Response(self._data(existing), status=200)
        try:
            opening, opened_at = quote(symbol)
        except (MarketDataError, ValueError) as exc:
            return Response({"code": "QUOTE_UNAVAILABLE", "message": "Market data is delayed. New demo trades are temporarily unavailable."}, status=409)
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=request.user, name=DEMO_WALLET_NAME, is_real=False, is_archived=False)
            if wallet.balance < amount:
                return Response({"code": "INSUFFICIENT_FUNDS", "message": "Your virtual balance is insufficient."}, status=409)
            asset_type, _ = AssetType.objects.get_or_create(name="Crypto")
            asset, _ = Asset.objects.get_or_create(symbol=symbol, defaults={"name": symbol, "asset_type": asset_type})
            category, _ = TradeCategory.objects.get_or_create(name="fixed")
            wallet.balance -= amount
            wallet.save(update_fields=["balance", "updated_at"])
            txn = Transaction.objects.create(wallet=wallet, type="TD", amount=-amount, status="S", gateway="demo", reference=f"demo:{request.user.pk}:{key}")
            trade = Trade.objects.create(wallet=wallet, asset=asset, quantity=Decimal("1"), price_per_unit=amount, transaction=txn, trade_type=direction, category=category, duration=duration, result_time=opened_at + timedelta(seconds=duration), expires_at=opened_at + timedelta(seconds=duration), opening_price=opening, open=opening, idempotency_key=f"demo:{request.user.pk}:{key}", demo_state="OPEN")
            DemoLedgerEntry.objects.create(wallet=wallet, trade=trade, entry_type="RESERVE", amount=Decimal("0"), idempotency_key=f"reserve:{trade.pk}", description="Virtual funds reserved")
        return Response(self._data(trade), status=201)

    def _data(self, trade):
        return {"id": trade.pk, "state": trade.demo_state, "result": trade.demo_result or None, "symbol": trade.asset.symbol, "direction": trade.trade_type, "amount": str(trade.price_per_unit), "openingPrice": str(trade.opening_price), "closingPrice": str(trade.closing_price) if trade.closing_price else None, "openedAt": trade.created_at.isoformat(), "expiresAt": trade.expires_at.isoformat()}


class DemoTradeListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        settle_due_orders()
        trades = Trade.objects.filter(wallet__user=request.user, wallet__is_real=False).select_related("asset").order_by("-created_at")
        return Response([DemoOrderView()._data(t) for t in trades])
