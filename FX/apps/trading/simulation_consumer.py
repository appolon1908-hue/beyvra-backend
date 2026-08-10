"""JetStream consumer entry points for simulation-only order and realtime events."""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.foundation.services import consume_once
from apps.trading.application.simulation import process_created_order
from apps.trading.models import TradingOrder


def consume_order_created(envelope):
    order_id = envelope["payload"]["order_id"]
    return consume_once(envelope=envelope, consumer_name="simulated-order-router-v1", mutation=lambda: process_created_order(order_id))


def consume_realtime_projection(envelope):
    payload = envelope.get("payload", {})
    order = TradingOrder.objects.filter(pk=payload.get("order_id"), simulation=True).first() if payload.get("order_id") else None
    if not order:
        return False
    def mutation():
        async_to_sync(get_channel_layer().group_send)(
            f"trades_updates_{order.tenant_ref}_{order.subject_ref}",
            {"type": "simulation_update", "message": {**payload, "event_type": envelope["event_type"], "event_id": envelope["event_id"], "simulation": True}},
        )
    return consume_once(envelope=envelope, consumer_name="simulation-realtime-projection-v1", mutation=mutation)
