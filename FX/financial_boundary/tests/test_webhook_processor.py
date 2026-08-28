import hashlib
import json
import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from financial_boundary.models import FinancialIncident, ProcessedEvent, ProviderWebhookInbox
from financial_boundary.webhook_processor import (
    claim_webhook_batch,
    process_webhook_batch,
    release_expired_webhook_leases,
)


class ProviderWebhookProcessorTests(TestCase):
    def inbox(self, **overrides):
        body = json.dumps({
            "event_type": "financial.trade.execution.v1",
            "order_id": "opaque-order",
        }).encode("utf-8")
        payload_hash = hashlib.sha256(body).hexdigest()
        values = {
            "provider": "alpaca",
            "external_event_id": f"evt-{uuid.uuid4()}",
            "tenant_id": uuid.uuid4(),
            "payload_hash": payload_hash,
            "encrypted_payload": body,
            "payload_reference": "sha256:" + payload_hash,
            "signature_timestamp": timezone.now(),
            "status": ProviderWebhookInbox.Status.PENDING,
            "next_attempt_at": timezone.now(),
        }
        values.update(overrides)
        return ProviderWebhookInbox.objects.create(**values)

    def effect(self, envelope):
        FinancialIncident.objects.create(
            severity="LOW",
            type="WEBHOOK_TEST_EFFECT",
            candidate_sha="0" * 40,
            environment="isolated-test",
            safe_summary="webhook processor effect",
            evidence_hash=envelope.payload_hash,
        )

    def test_processes_pending_webhook_once_and_records_receipt(self):
        row = self.inbox()
        result = process_webhook_batch(handler=self.effect, lease_owner="test-worker")
        self.assertEqual(result.processed, 1)
        row.refresh_from_db()
        self.assertEqual(row.status, ProviderWebhookInbox.Status.PROCESSED)
        self.assertEqual(row.lease_owner, "")
        self.assertEqual(FinancialIncident.objects.count(), 1)
        self.assertEqual(ProcessedEvent.objects.count(), 1)

    def test_handler_failure_retries_then_dead_letters(self):
        row = self.inbox()

        def fail(_):
            raise RuntimeError("provider handler failed")

        first = process_webhook_batch(handler=fail, max_attempts=2)
        self.assertEqual(first.retried, 1)
        row.refresh_from_db()
        self.assertEqual(row.status, ProviderWebhookInbox.Status.PENDING)
        ProviderWebhookInbox.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))

        second = process_webhook_batch(handler=fail, max_attempts=2)
        self.assertEqual(second.dead_lettered, 1)
        row.refresh_from_db()
        self.assertEqual(row.status, ProviderWebhookInbox.Status.DEAD_LETTER)
        self.assertEqual(FinancialIncident.objects.count(), 0)
        self.assertEqual(ProcessedEvent.objects.count(), 0)

    def test_invalid_payload_dead_letters_without_business_effect(self):
        row = self.inbox(encrypted_payload=b"not-json")
        result = process_webhook_batch(handler=self.effect)
        self.assertEqual(result.dead_lettered, 1)
        row.refresh_from_db()
        self.assertEqual(row.status, ProviderWebhookInbox.Status.DEAD_LETTER)
        self.assertEqual(FinancialIncident.objects.count(), 0)

    def test_expired_processing_lease_is_released_and_reclaimed(self):
        row = self.inbox()
        claimed = claim_webhook_batch(limit=1, lease_seconds=1, lease_owner="old-worker")
        self.assertEqual([item.id for item in claimed], [row.id])
        ProviderWebhookInbox.objects.filter(pk=row.pk).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(release_expired_webhook_leases(), 1)
        reclaimed = claim_webhook_batch(limit=1, lease_owner="new-worker")
        self.assertEqual([item.id for item in reclaimed], [row.id])
        row.refresh_from_db()
        self.assertEqual(row.lease_owner, "new-worker")
        self.assertEqual(row.attempts, 2)
