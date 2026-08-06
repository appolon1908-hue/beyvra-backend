from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings
from django.utils import timezone

from .models import ProviderApproval, ProviderDefinition, ProviderGovernanceAudit, ProviderLicense
from .service import ProviderNotAvailable, resolve_provider
from .pipeline import publish_governed_event
from unittest.mock import AsyncMock
from asgiref.sync import async_to_sync


class GovernanceResolutionTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.override = override_settings(PROVIDER_CREDENTIAL_ROOT=self.tmp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.provider = ProviderDefinition.objects.create(provider_id="deterministic_test", provider_type="MARKET_DATA", enabled=True)

    def records(self, *, approval_status="APPROVED", license_status="APPROVED", expires_at=None):
        credential = Path(self.tmp.name) / "market/test.key"
        credential.parent.mkdir(exist_ok=True)
        credential.write_text("never-returned")
        credential.chmod(0o600)
        ProviderLicense.objects.create(provider=self.provider, environment="STAGING", status=license_status, license_reference="license:test")
        ProviderApproval.objects.create(
            provider=self.provider, provider_type="MARKET_DATA", environment="STAGING",
            status=approval_status, approved_by="governance-test", approved_at=timezone.now(),
            expires_at=expires_at, approval_reference="approval:test", license_reference="license:test",
            credential_reference="market/test.key", allowed_products=["HISTORICAL_CANDLES"],
            allowed_symbols=["TEST"], allowed_regions=["GLOBAL"],
        )

    def resolve(self):
        return resolve_provider(provider_id="deterministic_test", provider_type="MARKET_DATA", product="HISTORICAL_CANDLES", symbol="TEST", region="GLOBAL")

    def test_approved_deterministic_provider_resolves_without_exposing_secret(self):
        self.records()
        resolved = self.resolve()
        self.assertEqual(resolved.provider_id, "deterministic_test")
        self.assertNotIn("never-returned", repr(resolved))
        self.assertEqual(ProviderGovernanceAudit.objects.get().decision, "ALLOWED")

    def test_pending_rejected_suspended_and_expired_are_denied(self):
        for status in ("PENDING", "REJECTED", "SUSPENDED", "EXPIRED"):
            ProviderApproval.objects.all().delete(); ProviderLicense.objects.all().delete()
            self.records(approval_status=status)
            with self.assertRaises(ProviderNotAvailable): self.resolve()

    def test_expired_approval_is_denied(self):
        self.records(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(ProviderNotAvailable): self.resolve()

    def test_missing_license_or_credential_is_denied(self):
        self.records(license_status="PENDING")
        with self.assertRaises(ProviderNotAvailable): self.resolve()
        self.assertEqual(ProviderGovernanceAudit.objects.first().decision, "DENIED")

    def test_disabled_or_missing_approval_is_denied(self):
        self.provider.enabled = False
        self.provider.save(update_fields=["enabled"])
        with self.assertRaises(ProviderNotAvailable): self.resolve()
        self.provider.enabled = True
        self.provider.save(update_fields=["enabled"])
        with self.assertRaises(ProviderNotAvailable): self.resolve()

    def test_wrong_environment_type_scope_and_expired_license_are_denied(self):
        self.records()
        approval = ProviderApproval.objects.get()
        approval.environment = "PRODUCTION"
        approval.save(update_fields=["environment"])
        with self.assertRaises(ProviderNotAvailable): self.resolve()
        approval.environment = "STAGING"; approval.provider_type = "FINANCIAL_NEWS"
        approval.save(update_fields=["environment", "provider_type"])
        with self.assertRaises(ProviderNotAvailable): self.resolve()
        approval.provider_type = "MARKET_DATA"; approval.allowed_symbols = ["OTHER"]
        approval.save(update_fields=["provider_type", "allowed_symbols"])
        with self.assertRaises(ProviderNotAvailable): self.resolve()
        approval.allowed_symbols = ["TEST"]
        approval.save(update_fields=["allowed_symbols"])
        license_record = ProviderLicense.objects.get()
        license_record.expires_at = timezone.now() - timedelta(seconds=1)
        license_record.save(update_fields=["expires_at"])
        with self.assertRaises(ProviderNotAvailable): self.resolve()

    def test_insecure_or_missing_credential_is_denied(self):
        self.records()
        credential = Path(self.tmp.name) / "market/test.key"
        credential.chmod(0o644)
        with self.assertRaises(ProviderNotAvailable): self.resolve()
        credential.unlink()
        with self.assertRaises(ProviderNotAvailable): self.resolve()

    def test_approved_deterministic_event_publishes_to_nats_without_secret(self):
        self.records()
        jetstream = AsyncMock()
        async_to_sync(publish_governed_event)(
            jetstream=jetstream,
            provider_id="deterministic_test",
            product="HISTORICAL_CANDLES",
            symbol="TEST",
            region="GLOBAL",
            subject="market.candle.TEST.1m",
            envelope={"type": "event", "channel": "market.candle.TEST.1m", "payload": {"close": "1.00"}},
        )
        jetstream.publish.assert_awaited_once()
        published = jetstream.publish.await_args.args[1]
        self.assertNotIn(b"never-returned", published)
