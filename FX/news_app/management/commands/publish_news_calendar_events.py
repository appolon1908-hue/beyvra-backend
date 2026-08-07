"""Publish committed news/calendar outbox rows to the existing JetStream."""

import asyncio
import json
import os
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone

from news_app.events import envelope, jetstream_subject
from news_app.models import NewsCalendarEventOutbox


async def _publish(rows):
    from nats.aio.client import Client as NATS

    client = NATS()
    await client.connect(os.getenv("NATS_URL", "nats://nats:4222"))
    stream = client.jetstream()
    results = []
    try:
        for event in rows:
            try:
                await stream.publish(jetstream_subject(event), json.dumps(envelope(event), separators=(",", ":"), default=str).encode(), headers={"Nats-Msg-Id": str(event.event_id)})
                results.append((event.sequence, None))
            except Exception as exc:
                results.append((event.sequence, type(exc).__name__[:64]))
                break
    finally:
        await client.drain()
    return results


def publish_batch(limit=100):
    rows = list(NewsCalendarEventOutbox.objects.filter(published_at__isnull=True).order_by("sequence")[:limit])
    if not rows:
        return 0
    published = 0
    for sequence, error in asyncio.run(_publish(rows)):
        if error is None:
            published += NewsCalendarEventOutbox.objects.filter(sequence=sequence, published_at__isnull=True).update(published_at=timezone.now(), attempt_count=F("attempt_count") + 1, last_error_code="")
        else:
            NewsCalendarEventOutbox.objects.filter(sequence=sequence).update(attempt_count=F("attempt_count") + 1, next_attempt_at=timezone.now() + timedelta(seconds=5), last_error_code=error)
    return published


class Command(BaseCommand):
    help = "Publish governed news/calendar events through the existing JetStream."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        if os.getenv("NATS_JETSTREAM_ENABLED", "false").lower() != "true":
            self.stdout.write("News/calendar event publisher disabled")
            return
        while True:
            count = publish_batch()
            if options["once"]:
                self.stdout.write(f"published={count}")
                return
            if not count:
                import time
                time.sleep(1)
