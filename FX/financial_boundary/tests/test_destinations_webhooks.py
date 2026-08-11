from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import time
import uuid

from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from financial_boundary.destinations import (
    DestinationAccessDenied, DestinationValidationError, create_destination,
    get_destination_for_withdrawal, revoke_destination,
)
from financial_boundary.eventing import EventContractError
from financial_boundary.models import Destination, FinancialIncident, ProcessedEvent
from financial_boundary.webhooks import (
    WebhookDenied, consume_verified_webhook, verify_provider_webhook, webhook_signature,
)


@override_settings(DESTINATION_FINGERPRINT_KEY="isolated-test-key-material-32-bytes-minimum")
class DestinationBoundaryTests(TransactionTestCase):
    def setUp(self):
        self.tenant = uuid.uuid4()
        self.account = uuid.uuid4()
        self.owner = 41
        self.raw = "0x1111111111111111111111111111111111111111"

    def create(self, **changes):
        values = dict(
            tenant_ref=self.tenant, account_ref=self.account, owner_ref=self.owner,
            destination_type=Destination.Type.CRYPTO, asset="ETH", network="ETHEREUM",
            value=self.raw, beneficiary_ref=uuid.uuid4(),
        )
        values.update(changes)
        return create_destination(**values)

    def test_destination_persists_only_mask_and_keyed_fingerprint(self):
        destination = self.create()
        self.assertEqual(destination.status, Destination.Status.PENDING)
        self.assertEqual(destination.masked_display, "0x1111…1111")
        self.assertEqual(len(destination.destination_fingerprint), 64)
        persisted = Destination.objects.values().get(pk=destination.pk)
        self.assertNotIn(self.raw, repr(persisted))
        self.assertFalse(any("address" in field.name or "value" in field.name for field in Destination._meta.fields))

        fiat_raw = "provider:bank_fixture:customer:opaque_123456"
        fiat = self.create(
            destination_type=Destination.Type.FIAT, asset="USD", network="PROVIDER_REFERENCE",
            value=fiat_raw,
        )
        self.assertEqual(fiat.masked_display, "provider:bank_fixture:customer:…3456")
        self.assertNotIn(fiat_raw, repr(Destination.objects.values().get(pk=fiat.pk)))

    def test_network_syntax_and_opaque_fiat_reference_are_enforced(self):
        invalid = [
            dict(asset="BTC", network="BITCOIN", value=self.raw),
            dict(asset="BTC", network="ETHEREUM", value=self.raw),
            dict(asset="BTC", network="BITCOIN_TESTNET", value="bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"),
            dict(asset="ETH", network="UNKNOWN", value=self.raw),
            dict(destination_type=Destination.Type.FIAT, asset="USD", network="PROVIDER_REFERENCE", value="DE123456789"),
        ]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(DestinationValidationError):
                self.create(**changes)

    def test_cross_scope_lookup_is_non_enumerable_and_revocation_is_fail_closed(self):
        destination = self.create(cooldown=timedelta(0))
        for scope in (
            dict(tenant_ref=uuid.uuid4(), account_ref=self.account, owner_ref=self.owner),
            dict(tenant_ref=self.tenant, account_ref=uuid.uuid4(), owner_ref=self.owner),
            dict(tenant_ref=self.tenant, account_ref=self.account, owner_ref=self.owner + 1),
        ):
            with self.assertRaises(DestinationAccessDenied) as denied:
                get_destination_for_withdrawal(destination_id=destination.pk, **scope)
            self.assertEqual(denied.exception.code, "DESTINATION_NOT_FOUND")

        with self.assertRaises(DestinationValidationError):
            get_destination_for_withdrawal(
                destination_id=destination.pk, tenant_ref=self.tenant,
                account_ref=self.account, owner_ref=self.owner,
            )
        Destination.objects.filter(pk=destination.pk).update(
            status=Destination.Status.VERIFIED, verified_at=timezone.now(),
            cooldown_until=timezone.now() + timedelta(hours=1),
        )
        with self.assertRaisesRegex(DestinationValidationError, "DESTINATION_COOLDOWN"):
            get_destination_for_withdrawal(
                destination_id=destination.pk, tenant_ref=self.tenant,
                account_ref=self.account, owner_ref=self.owner,
            )
        Destination.objects.filter(pk=destination.pk).update(cooldown_until=timezone.now())
        self.assertEqual(get_destination_for_withdrawal(
            destination_id=destination.pk, tenant_ref=self.tenant,
            account_ref=self.account, owner_ref=self.owner,
        ).pk, destination.pk)
        revoke_destination(
            destination_id=destination.pk, tenant_ref=self.tenant,
            account_ref=self.account, owner_ref=self.owner,
        )
        with self.assertRaises(DestinationValidationError):
            get_destination_for_withdrawal(
                destination_id=destination.pk, tenant_ref=self.tenant,
                account_ref=self.account, owner_ref=self.owner,
            )


class ProviderWebhookBoundaryTests(TransactionTestCase):
    reset_sequences = True
    secret = b"isolated-fixture-webhook-secret-material"
    provider = "custody_fixture"

    def build(self, *, payload=None, event_id="evt_fixture_0001", timestamp=None, provider=None, secret=None):
        timestamp = int(time.time()) if timestamp is None else timestamp
        provider = provider or self.provider
        secret = secret or self.secret
        body = json.dumps(payload or {
            "event_type": "financial.withdrawal.updated.v1",
            "withdrawal_ref": "opaque-withdrawal", "state": "PENDING_CONFIRMATION",
        }, separators=(",", ":")).encode()
        headers = {
            "X-Provider-Id": provider, "X-Event-Id": event_id,
            "X-Timestamp": str(timestamp),
            "X-Signature": webhook_signature(
                provider_id=provider, event_id=event_id, timestamp=timestamp,
                raw_body=body, secret=secret,
            ),
        }
        return headers, body

    @staticmethod
    def effect(envelope):
        FinancialIncident.objects.create(
            severity="LOW", type="WEBHOOK_TEST_EFFECT", candidate_sha="0" * 40,
            environment="isolated-test", safe_summary="verified fixture effect",
            evidence_hash=envelope.payload_hash,
        )

    def test_invalid_identity_signature_timestamp_and_secret_payload_have_no_effect(self):
        tenant = uuid.uuid4()
        cases = []
        headers, body = self.build()
        cases.append(({**headers, "X-Signature": "v1=" + "0" * 64}, body))
        cases.append(self.build(timestamp=int(time.time()) - 301))
        cases.append(self.build(provider="other_provider"))
        cases.append(self.build(payload={"event_type": "financial.deposit.updated.v1", "private_key": "never"}))
        for case_headers, case_body in cases:
            with self.subTest(headers=case_headers), self.assertRaises((WebhookDenied, EventContractError)):
                verify_provider_webhook(
                    expected_provider_id=self.provider, tenant_ref=tenant,
                    headers=case_headers, raw_body=case_body, secret=self.secret,
                )
        self.assertEqual(ProcessedEvent.objects.count(), 0)
        self.assertEqual(FinancialIncident.objects.count(), 0)

    def test_one_hundred_concurrent_duplicate_webhooks_have_one_effect(self):
        tenant = uuid.uuid4()
        headers, body = self.build()
        webhook = verify_provider_webhook(
            expected_provider_id=self.provider, tenant_ref=tenant,
            headers=headers, raw_body=body, secret=self.secret,
        )

        def deliver(_):
            close_old_connections()
            try:
                return consume_verified_webhook(webhook, self.effect)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=20) as executor:
            outcomes = list(executor.map(deliver, range(100)))
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 99)
        self.assertEqual(ProcessedEvent.objects.count(), 1)
        self.assertEqual(FinancialIncident.objects.count(), 1)
        receipt = ProcessedEvent.objects.get()
        self.assertFalse(hasattr(receipt, "payload"))
        self.assertEqual(len(receipt.payload_hash), 64)
