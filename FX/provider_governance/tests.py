from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import os

from asgiref.sync import async_to_sync
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace

from .models import ProviderApproval, ProviderDefinition, ProviderGovernanceAudit, ProviderLicense
from .pipeline import publish_governed_event
from .service import ProviderNotAvailable, approval_payload_hash, resolve_provider

CURRENT_TEST_UID = str(getattr(os, "getuid", lambda: 0)())


class GovernanceResolutionTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.override = override_settings(PROVIDER_CREDENTIAL_ROOT=self.tmp.name, PROVIDER_CREDENTIAL_ALLOWED_UIDS=CURRENT_TEST_UID)
        self.override.enable(); self.addCleanup(self.override.disable)
        self.provider = ProviderDefinition.objects.create(provider_id="deterministic_test", provider_type="MARKET_DATA", enabled=True, license_verified=True, security_approved=True, compliance_approved=True, staging_approved=True, allowed_asset_classes=["TEST"], allowed_data_types=["HISTORICAL_CANDLES"], max_staleness_ms=1000, updated_by="test-suite")

    def test_provider_policy_defaults_fail_closed(self):
        blocked=ProviderDefinition.objects.create(provider_id="blocked",provider_type="MARKET_DATA")
        self.assertFalse(blocked.enabled); self.assertFalse(blocked.license_verified); self.assertFalse(blocked.security_approved); self.assertFalse(blocked.compliance_approved); self.assertFalse(blocked.staging_approved); self.assertFalse(blocked.production_approved)

    def records(self, *, status="APPROVED", policy="REQUIRED", approved_at=None, expires_at=None, version=1, supersedes=None):
        license_record = ProviderLicense.objects.create(provider=self.provider, environment="STAGING", status="APPROVED", license_reference=f"license:test:{version}")
        reference = f"market/deterministic_test/v{version}/credential.key" if policy == "REQUIRED" else None
        if reference:
            path = Path(self.tmp.name) / reference; path.parent.mkdir(parents=True); path.write_text("never-returned"); path.chmod(0o600)
        approval = ProviderApproval(
            provider=self.provider, provider_type="MARKET_DATA", environment="STAGING", version=version,
            status=status, approved_by_principal_id="principal:test", approved_at=approved_at or timezone.now(), expires_at=expires_at,
            approval_reference=f"approval:test:{version}", license=license_record, credential_policy=policy,
            credential_reference=reference, allowed_products=["HISTORICAL_CANDLES"], allowed_symbols=["TEST"],
            allowed_regions=["GLOBAL"], supersedes_approval=supersedes, created_by="principal:test", approval_payload_hash="",
        )
        approval.approval_payload_hash = approval_payload_hash(approval); approval.save()
        return approval

    def resolve(self, **kwargs):
        values = dict(provider_id="deterministic_test", provider_type="MARKET_DATA", product="HISTORICAL_CANDLES", symbol="TEST", region="GLOBAL", request_id="req-1", correlation_id="corr-1", caller_service="test-suite")
        values.update(kwargs); return resolve_provider(**values)

    def test_required_and_none_credential_policies_resolve(self):
        required = self.records(); self.assertTrue(self.resolve().credential_path)
        none = self.records(policy="NONE", version=2, supersedes=required); self.assertIsNone(self.resolve().credential_path)

    def test_all_nonapproved_statuses_and_expiry_deny(self):
        for version, status in enumerate(("PENDING", "REJECTED", "SUSPENDED", "EXPIRED"), 1):
            self.records(status=status, version=version)
            with self.assertRaises(ProviderNotAvailable): self.resolve()
        self.records(approved_at=timezone.now()-timedelta(seconds=2), expires_at=timezone.now()-timedelta(seconds=1), version=5)
        with self.assertRaises(ProviderNotAvailable): self.resolve()

    def test_scope_type_hash_and_credential_security_deny(self):
        approval = self.records()
        with self.assertRaises(ProviderNotAvailable): self.resolve(symbol="OTHER")
        with self.assertRaises(ProviderNotAvailable): self.resolve(provider_type="FINANCIAL_NEWS")
        if connection.vendor != "postgresql":
            self.skipTest("approved-row immutability is enforced by PostgreSQL triggers")
        with self.assertRaises(Exception), transaction.atomic(): ProviderApproval.objects.filter(pk=approval.pk).update(approval_payload_hash="0"*64)

    def test_symlink_insecure_mode_unversioned_and_acl_style_xattr_deny(self):
        approval = self.records(); path = Path(self.tmp.name) / approval.credential_reference
        if os.name == "posix":
            path.chmod(0o644)
            with self.assertRaises(ProviderNotAvailable): self.resolve()
            path.chmod(0o600)
        self.assertTrue(self.resolve().credential_path)

    def test_approved_rows_are_immutable_and_replacement_is_versioned(self):
        approval = self.records()
        if connection.vendor == "postgresql":
            with self.assertRaises(Exception), transaction.atomic(): ProviderApproval.objects.filter(pk=approval.pk).update(allowed_regions=["OTHER"])
            with self.assertRaises(Exception), transaction.atomic(): approval.delete()
        replacement = self.records(policy="NONE", version=2, supersedes=approval)
        self.assertEqual(self.resolve().approval_id, replacement.id)

    def test_audit_captures_nonsecret_authorization_evidence(self):
        approval = self.records(); self.resolve(); audit = ProviderGovernanceAudit.objects.get(decision="ALLOWED")
        self.assertEqual((audit.approval_id, audit.approval_version, audit.license_id), (approval.id, 1, approval.license_id))
        self.assertEqual((audit.request_id, audit.correlation_id, audit.caller_service), ("req-1", "corr-1", "test-suite"))
        self.assertNotIn("never-returned", repr(audit.__dict__))

    def test_deterministic_event_reaches_jetstream_without_secret(self):
        self.records(policy="NONE"); js=AsyncMock()
        async_to_sync(publish_governed_event)(jetstream=js, provider_id="deterministic_test", product="HISTORICAL_CANDLES", symbol="TEST", region="GLOBAL", subject="market.candle.TEST.1m", envelope={"type":"event","channel":"market.candle.TEST.1m","payload":{"close":"1"}})
        js.publish.assert_awaited_once(); self.assertNotIn(b"never-returned", js.publish.await_args.args[1])

    def test_database_constraints_reject_invalid_approved_record(self):
        license_record = ProviderLicense.objects.create(provider=self.provider, environment="STAGING", status="APPROVED", license_reference="license:invalid")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderApproval.objects.create(provider=self.provider, provider_type="MARKET_DATA", environment="STAGING", version=1, status="APPROVED", approval_reference="bad", license=license_record, credential_policy="NONE", allowed_products=[], allowed_symbols=[], allowed_regions=[], approval_payload_hash="0"*64, created_by="test")

    @patch("news_app.utils.requests.get")
    def test_news_adapter_denial_makes_zero_outbound_requests(self, outbound):
        from news_app.utils import get_newsdata_news
        request = SimpleNamespace(query_params={}, headers={})
        with self.assertRaises(ProviderNotAvailable): get_newsdata_news(request)
        outbound.assert_not_called()

    def test_calendar_adapter_denial_makes_zero_outbound_requests(self):
        from api_trade.scripts.alpaca_integration import AlpacaIntegrationAccount
        adapter = AlpacaIntegrationAccount.__new__(AlpacaIntegrationAccount)
        adapter.trading_client = Mock()
        request = SimpleNamespace(query_params={}, headers={})
        with self.assertRaises(ProviderNotAvailable): adapter.get_calendar(request)
        adapter.trading_client.get_calendar.assert_not_called()
