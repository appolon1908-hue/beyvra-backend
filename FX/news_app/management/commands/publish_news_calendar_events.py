"""Deprecated compatibility alias for the canonical outbox publisher."""

import os

from django.core.management.base import BaseCommand
from apps.foundation.publisher import publish_batch


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
