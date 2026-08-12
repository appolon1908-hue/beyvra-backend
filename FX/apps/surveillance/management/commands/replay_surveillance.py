import json

from django.core.management.base import BaseCommand, CommandError

from apps.surveillance.engine import SurveillanceEngine


class Command(BaseCommand):
    help = "Evaluate a sanitized synthetic event file without mutating normal surveillance state"
    def add_arguments(self, parser): parser.add_argument("fixture")
    def handle(self, *args, **options):
        try:
            with open(options["fixture"], encoding="utf-8") as source:
                events = json.load(source)
        except (OSError, ValueError) as exc:
            raise CommandError("invalid replay fixture") from exc
        findings = SurveillanceEngine().evaluate_window(events)
        self.stdout.write(json.dumps({"replay": True, "mutations": 0, "findings": [{"event_type": row.event_type, "severity": row.severity, "score": str(row.score), "rule_version": row.rule_version, "policy_version": row.policy_version} for row in findings]}, sort_keys=True))
