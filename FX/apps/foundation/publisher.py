import asyncio
import json
import os
import ssl

from django.conf import settings

from .services import claim_outbox_batch, mark_publish_result
from .observability import OUTBOX_FAILURES, OUTBOX_LAST_SUCCESS, OUTBOX_PUBLISHED, OUTBOX_RETRIES, worker_success

CANONICAL_SUBJECT_DOMAINS = {
    "trading",
    "post_trade",
    "valuation",
    "treasury",
    "regulatory",
    "compliance",
    "market",
    "news",
    "private",
    "system",
    "identity",
}


def subject_for(event_type):
    subject = str(event_type).strip()
    domain = subject.split(".", 1)[0]
    if domain not in CANONICAL_SUBJECT_DOMAINS or "." not in subject:
        raise ValueError("NON_CANONICAL_EVENT_SUBJECT")
    return subject


def envelope(event):
    result = {
        "event_id": str(event.event_id), "event_type": event.event_type,
        "schema_version": event.schema_version, "occurred_at": event.occurred_at.isoformat(),
        "correlation_id": str(event.correlation_id),
        "causation_id": str(event.causation_id) if event.causation_id else None,
        "tenant_ref": event.tenant_ref, "payload": event.payload,
    }
    if isinstance(event.payload, dict):
        if "channel" in event.payload:
            result["channel"] = event.payload["channel"]
        if "data" in event.payload:
            result["data"] = event.payload["data"]
    return result


async def _publish(rows):
    from nats.aio.client import Client as NATS
    client = NATS()
    tls_context = None
    if ca_file := os.getenv("NATS_TLS_CA_FILE"):
        tls_context = ssl.create_default_context(cafile=ca_file)
        if cert_file := os.getenv("NATS_TLS_CERT_FILE"):
            tls_context.load_cert_chain(cert_file, os.getenv("NATS_TLS_KEY_FILE"))
    await client.connect(os.getenv("NATS_URL", "nats://nats:4222"), tls=tls_context)
    stream = client.jetstream()
    results = []
    try:
        for event in rows:
            try:
                subject = subject_for(event.event_type)
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
        if error:
            OUTBOX_FAILURES.labels("dependency").inc(); OUTBOX_RETRIES.inc()
        else:
            OUTBOX_PUBLISHED.inc(); OUTBOX_LAST_SUCCESS.set(__import__("time").time()); worker_success("outbox_publisher")
        published += not bool(error)
    return published
