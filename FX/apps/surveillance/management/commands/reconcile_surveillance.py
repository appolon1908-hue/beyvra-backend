import json

from django.core.management.base import BaseCommand, CommandError

from apps.surveillance.reconciliation import reconcile_surveillance


class Command(BaseCommand):
    help = "Run read-only market-surveillance reconciliation"
    def handle(self, *args, **options):
        report = reconcile_surveillance()
        self.stdout.write(json.dumps(report, sort_keys=True))
        if report["status"] != "PASS": raise CommandError("surveillance reconciliation failed")
