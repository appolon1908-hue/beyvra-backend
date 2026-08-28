from django.core.management.base import BaseCommand

from financial_boundary.webhook_processor import process_webhook_batch


class Command(BaseCommand):
    help = "Process verified provider webhooks from the durable inbox."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--lease-seconds", type=int, default=30)
        parser.add_argument("--max-attempts", type=int, default=5)
        parser.add_argument("--lease-owner", default="")

    def handle(self, *args, **options):
        result = process_webhook_batch(
            limit=options["limit"],
            lease_seconds=options["lease_seconds"],
            max_attempts=options["max_attempts"],
            lease_owner=options["lease_owner"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                "provider_webhooks "
                f"claimed={result.claimed} processed={result.processed} "
                f"duplicates={result.duplicates} retried={result.retried} "
                f"dead_lettered={result.dead_lettered}"
            )
        )
