"""Publish committed demo-event outbox rows to the existing JetStream."""

import asyncio
import json
import os
import ssl
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone

from trade.demo_events import envelope, jetstream_subject
from trade.models import DemoEventOutbox


def _tls_context():
    ca_file = os.getenv("NATS_TLS_CA_FILE")
    if not ca_file:
        return None
    context = ssl.create_default_context(cafile=ca_file)
    cert_file = os.getenv("NATS_TLS_CERT_FILE")
    key_file = os.getenv("NATS_TLS_KEY_FILE")
    if cert_file and key_file:
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    return context


async def _publish(rows):
    from nats.aio.client import Client as NATS

    nc = NATS()
    await nc.connect(os.getenv("NATS_URL", "nats://nats:4222"), tls=_tls_context())
    js = nc.jetstream()
    results = []
    try:
        for event in rows:
            try:
                await js.publish(
                    jetstream_subject(event),
                    json.dumps(envelope(event), separators=(",", ":")).encode(),
                    headers={"Nats-Msg-Id": str(event.event_id)},
                )
                results.append((event.sequence, None))
            except Exception as exc:
                results.append((event.sequence, type(exc).__name__[:64]))
                break
    finally:
        await nc.drain()
    return results


def publish_batch(limit=100):
    rows = list(DemoEventOutbox.objects.filter(published_at__isnull=True).order_by("sequence")[:limit])
    if not rows:
        return 0
    results = asyncio.run(_publish(rows))
    published = 0
    for sequence, error in results:
        if error is None:
            published += DemoEventOutbox.objects.filter(sequence=sequence, published_at__isnull=True).update(
                published_at=timezone.now(), attempt_count=F("attempt_count") + 1, last_error_code=""
            )
        else:
            DemoEventOutbox.objects.filter(sequence=sequence).update(
                attempt_count=F("attempt_count") + 1,
                next_attempt_at=timezone.now() + timedelta(seconds=5),
                last_error_code=error,
            )
    return published


class Command(BaseCommand):
    help = "Publish committed account-scoped demo events through the approved JetStream."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        if os.getenv("NATS_JETSTREAM_ENABLED", "false").lower() != "true":
            self.stdout.write("Demo event publisher disabled")
            return
        while True:
            count = publish_batch()
            if options["once"]:
                self.stdout.write(f"published={count}")
                return
            if not count:
                import time
                time.sleep(1)
