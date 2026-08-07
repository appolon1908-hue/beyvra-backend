from datetime import datetime
from decimal import Decimal

from celery import shared_task
from channels.layers import get_channel_layer
from fx_utils.constants import DATE_FORMAT
from trade.models import Trade
from trade.demo_engine import settle_due_orders

channel_layer = get_channel_layer()


@shared_task
def print_ok():
    """A simple task that returns 'ok'. Used for testing purposes."""
    return "ok"


@shared_task
def settle_demo_orders():
    return settle_due_orders()


@shared_task
def update_active_trades(open: int, close: int, time: str) -> None:
    """Update active trades"""
    now = datetime.strptime(time, DATE_FORMAT)
    trades = Trade.objects.filter(is_active=True, result_time__lte=now, category__name="fixed", wallet__is_real=False)
    for t in trades:
        winner = False
        if t.trade_type == "up":
            winner = close > float(t.close)
        elif t.trade_type == "down":
            winner = close < float(t.close)
        amount = t.quantity * t.price_per_unit
        if winner:
            t.net = amount * Decimal("0.8")
        else:
            t.net = Decimal("0") - amount
        t.is_active = False
        t.save()
        # update wallet
        # TODO: update transaction
        if t.net > 0:
            wallet = t.wallet
            wallet.balance += t.net + amount
            wallet.save()
