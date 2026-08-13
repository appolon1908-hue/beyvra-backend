import os
import time

from django.core.cache import cache
from django.core.management.base import BaseCommand

from apps.foundation.publisher import publish_batch
from apps.foundation.observability import WORKER_RESTARTS, WORKER_UP, WORKER_FAILURES


class Command(BaseCommand):
    help = "Publish the canonical transactional application outbox."
    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
    def handle(self, *_args, **options):
        if os.getenv("NATS_JETSTREAM_ENABLED", "false").lower() != "true":
            self.stdout.write("Application outbox publisher disabled")
            return
        WORKER_RESTARTS.labels("outbox_publisher").inc(); WORKER_UP.labels("outbox_publisher").set(1)
        while True:
            cache.set("health:outbox-worker", "1", 30)
            try: count = publish_batch()
            except Exception:
                WORKER_FAILURES.labels("outbox_publisher","dependency").inc(); WORKER_UP.labels("outbox_publisher").set(0); raise
            if options["once"]:
                self.stdout.write(f"published={count}")
                return
            if not count:
                time.sleep(1)
