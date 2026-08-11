import json

from django.core.management.base import BaseCommand, CommandError

from reference_data.reconciliation import run_reference_data_reconciliation


class Command(BaseCommand):
    help = "Run read-only instrument/reference-data reconciliation"

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        report = run_reference_data_reconciliation()
        if options["json"]:
            self.stdout.write(json.dumps(report, sort_keys=True))
        else:
            self.stdout.write(f"RECONCILIATION={report['status']} CHECKS={report['checks']} VIOLATIONS={len(report['violations'])}")
        if report["status"] != "PASS":
            raise CommandError("Reference-data reconciliation failed")
