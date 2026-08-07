"""Authoritative demo-order events committed with demo state changes."""

from decimal import Decimal

from django.utils import timezone

from .models import DemoEventOutbox, Trade


ORDER_CHANNEL = "demo.order"
EXECUTION_CHANNEL = "demo.execution"


def _decimal(value):
    return str(value) if value is not None else None


def trade_payload(trade: Trade, *, status: str, settled_at=None) -> dict:
    opened_at = trade.created_at
    return {
        "id": str(trade.pk),
        "trade_id": str(trade.pk),
        "account_id": str(trade.wallet_id),
        "tenant_id": str(trade.organization_id),
        "instrument_id": trade.asset.symbol,
        "symbol": trade.asset.symbol,
        "direction": trade.trade_type.upper(),
        "status": status,
        "state": status,
        "result": trade.demo_result or None,
        "open_time": opened_at.isoformat(),
        "open_price": _decimal(trade.opening_price),
        "expiry_time": trade.expires_at.isoformat() if trade.expires_at else None,
        "settlement_time": settled_at.isoformat() if settled_at else None,
        "settlement_price": _decimal(trade.closing_price),
        "amount": _decimal(trade.price_per_unit),
        "payout_percent": _decimal(Decimal("80")),
    }


def enqueue_trade_event(trade: Trade, event_type: str, *, status: str, settled_at=None) -> DemoEventOutbox:
    if not trade.organization_id or not trade.wallet_id:
        raise ValueError("Demo events require tenant and account ownership")
    channel = ORDER_CHANNEL if event_type.startswith("demo.order.") else EXECUTION_CHANNEL
    event = DemoEventOutbox.objects.create(
        event_type=event_type,
        channel=channel,
        organization_id=trade.organization_id,
        wallet_id=trade.wallet_id,
        trade_id=trade.pk,
        payload=trade_payload(trade, status=status, settled_at=settled_at),
        occurred_at=timezone.now(),
    )
    event.payload["status_version"] = event.sequence
    event.save(update_fields=["payload"])
    return event


def envelope(event: DemoEventOutbox) -> dict:
    occurred = event.occurred_at.isoformat()
    return {
        "type": "event",
        "event_id": f"evt_{event.event_id.hex}",
        "event_type": event.event_type,
        "event_version": event.event_version,
        "channel": f"{event.channel}:{event.wallet_id}",
        "sequence": event.sequence,
        "account_id": str(event.wallet_id),
        "tenant_id": str(event.organization_id),
        "instrument_id": event.payload.get("instrument_id"),
        "occurred_at": occurred,
        "server_time": timezone.now().isoformat(),
        "source": "codestra-demo-order-service",
        "data": event.payload,
    }


def jetstream_subject(event: DemoEventOutbox) -> str:
    kind = "order" if event.channel == ORDER_CHANNEL else "trade"
    return f"private.{kind}.{event.wallet_id}"
