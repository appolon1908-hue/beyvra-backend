from apps.foundation.services import enqueue_event


def enqueue_order_event(order, event_type, payload, *, correlation_id, causation_id=None):
    if not event_type.startswith("trading.order.") or not event_type.endswith(".v1"):
        raise ValueError("ORDER_EVENT_TYPE_MUST_BE_VERSIONED")
    return enqueue_event(
        aggregate_type="order",
        aggregate_id=order.pk,
        event_type=event_type,
        payload=payload,
        tenant_ref=order.tenant_ref,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
