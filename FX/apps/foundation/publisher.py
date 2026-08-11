import asyncio
import json
import os

from django.conf import settings

from .services import claim_outbox_batch, mark_publish_result


def envelope(event):
    result = {
        "event_id": str(event.event_id), "event_type": event.event_type,
        "schema_version": event.schema_version, "occurred_at": event.occurred_at.isoformat(),
        "correlation_id": str(event.correlation_id),
        "causation_id": str(event.causation_id) if event.causation_id else None,
        "tenant_ref": event.tenant_ref, "payload": event.payload,
    }
    if event.event_type.startswith("compliance."):
        result.update({"type":"event","channel":event.payload.get("channel"),"data":event.payload.get("data",{})})
    return result


async def _publish(rows):
    from nats.aio.client import Client as NATS
    client = NATS()
    await client.connect(os.getenv("NATS_URL", "nats://nats:4222"))
    stream = client.jetstream()
    results = []
    try:
        for event in rows:
            try:
                subject = f"private.{event.event_type}" if event.event_type.startswith("compliance.") else f"application.{event.event_type}"
                await stream.publish(subject, json.dumps(envelope(event), separators=(",", ":"), default=str).encode(), headers={"Nats-Msg-Id": str(event.event_id)})
                results.append((event, ""))
            except Exception as exc:
                results.append((event, type(exc).__name__))
                break
    finally:
        await client.drain()
    return results


def publish_batch(limit=100):
    rows = claim_outbox_batch(limit=limit)
    if not rows:
        return 0
    published = 0
    for event, error in asyncio.run(_publish(rows)):
        mark_publish_result(event, error_code=error, maximum_attempts=getattr(settings, "OUTBOX_MAX_ATTEMPTS", 10))
        published += not bool(error)
    return published
