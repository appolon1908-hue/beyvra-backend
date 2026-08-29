import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.test.utils import override_settings
from django.utils import timezone

from platform_ops.health.checks import check_email_delivery_configuration, check_identity_provider_configuration


class Command(BaseCommand):
    help = "Collect safe identity and email readiness evidence for release gates."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true", help="Collect live provider evidence with bounded network calls.")

    def handle(self, *args, **options):
        collect_live = bool(options["live"])
        context = override_settings(READINESS_COLLECT_LIVE_IDENTITY_EMAIL_EVIDENCE=True) if collect_live else None
        if context:
            context.enable()
        try:
            email_ok, email_latency, email_reason = check_email_delivery_configuration()
            identity_ok, identity_latency, identity_reason = check_identity_provider_configuration()
        finally:
            if context:
                context.disable()
        payload = {
            "collected_at": timezone.now().isoformat(),
            "environment": settings.DEPLOYMENT_ENV,
            "live_evidence_requested": collect_live,
            "readiness_enforced": settings.READINESS_ENFORCE_IDENTITY_EMAIL,
            "checks": {
                "email_delivery": {
                    "ok": email_ok,
                    "reason": email_reason,
                    "latency_ms": round(email_latency, 3),
                },
                "identity_provider": {
                    "ok": identity_ok,
                    "reason": identity_reason,
                    "latency_ms": round(identity_latency, 3),
                },
            },
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))
