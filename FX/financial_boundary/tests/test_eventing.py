from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import uuid

from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from financial_boundary.eventing import (
    EventContractError, EventReplayConflict, FinancialEventEnvelope,
    append_financial_audit, claim_outbox_batch, consume_financial_event,
    enqueue_financial_event, mark_outbox_published, record_dead_letter,
    release_expired_claims,
)
from financial_boundary.models import (
    DeadLetterEvent, FinancialAuditEvent, FinancialIncident,
    FinancialOutboxEvent, ProcessedEvent,
)


class FinancialEventBoundaryTests(TransactionTestCase):
    reset_sequences = True

    def envelope(self, **changes):
        values = {
            "event_id": uuid.uuid4(),
            "event_type": "financial.withdrawal.updated.v1",
            "schema_version": 1,
            "occurred_at": timezone.now(),
            "correlation_id": uuid.uuid4(),
            "causation_id": None,
            "tenant_ref": uuid.uuid4(),
            "payload": {"withdrawal_ref": "opaque-1", "state": "PENDING_APPROVAL"},
        }
        values.update(changes)
        return FinancialEventEnvelope(**values)

    def effect_handler(self, envelope):
        FinancialIncident.objects.create(
            severity="LOW", type="TEST_EFFECT", candidate_sha="0" * 40,
            environment="isolated-test", safe_summary="deterministic test effect",
            evidence_hash=envelope.payload_hash,
        )

    def test_envelope_is_versioned_and_rejects_secret_or_pii_subject_material(self):
        with self.assertRaises(EventContractError):
            self.envelope(event_type="withdrawal.updated")
        with self.assertRaises(EventContractError):
            self.envelope(event_type="financial.withdrawal.updated.v2")
        with self.assertRaises(EventContractError):
            self.envelope(payload={"private_key": "never"})
        with self.assertRaises(EventContractError):
            append_financial_audit(
                action="withdrawal.requested", tenant_ref=uuid.uuid4(),
                correlation_id=uuid.uuid4(), payload={}, subject_ref="person@example.com",
            )

    def test_domain_mutation_and_outbox_share_one_transaction(self):
        envelope = self.envelope()
        with self.assertRaises(RuntimeError):
            enqueue_financial_event(envelope)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                FinancialIncident.objects.create(
                    severity="LOW", type="ROLLBACK", candidate_sha="0" * 40,
                    environment="isolated-test", safe_summary="rollback fixture",
                    evidence_hash=envelope.payload_hash,
                )
                enqueue_financial_event(envelope)
                raise RuntimeError("synthetic crash before commit")
        self.assertEqual(FinancialIncident.objects.count(), 0)
        self.assertEqual(FinancialOutboxEvent.objects.count(), 0)

        with transaction.atomic():
            self.effect_handler(envelope)
            enqueue_financial_event(envelope)
        self.assertEqual(FinancialIncident.objects.count(), 1)
        self.assertEqual(FinancialOutboxEvent.objects.count(), 1)

    def test_one_hundred_duplicate_deliveries_have_one_business_effect(self):
        envelope = self.envelope()
        outcomes = [consume_financial_event(envelope, self.effect_handler) for _ in range(100)]
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 99)
        self.assertEqual(FinancialIncident.objects.count(), 1)
        self.assertEqual(ProcessedEvent.objects.count(), 1)

    def test_concurrent_duplicate_deliveries_have_one_business_effect(self):
        envelope = self.envelope()

        def deliver(_):
            close_old_connections()
            try:
                return consume_financial_event(envelope, self.effect_handler)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=20) as executor:
            outcomes = list(executor.map(deliver, range(100)))
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(FinancialIncident.objects.count(), 1)

    def test_handler_failure_rolls_back_receipt_and_retry_can_succeed(self):
        envelope = self.envelope()

        def fail(_):
            raise RuntimeError("synthetic consumer crash before commit")

        with self.assertRaises(RuntimeError):
            consume_financial_event(envelope, fail)
        self.assertFalse(ProcessedEvent.objects.filter(pk=envelope.event_id).exists())
        self.assertTrue(consume_financial_event(envelope, self.effect_handler))
        self.assertEqual(FinancialIncident.objects.count(), 1)

    def test_cross_tenant_or_changed_payload_replay_is_rejected(self):
        envelope = self.envelope()
        self.assertTrue(consume_financial_event(envelope, self.effect_handler))
        changed = self.envelope(
            event_id=envelope.event_id, correlation_id=envelope.correlation_id,
            tenant_ref=uuid.uuid4(), payload=envelope.payload,
        )
        with self.assertRaises(EventReplayConflict):
            consume_financial_event(changed, self.effect_handler)
        self.assertEqual(FinancialIncident.objects.count(), 1)

    def test_poison_event_dead_letter_is_durable_and_contains_no_payload(self):
        envelope = self.envelope(payload={"destination_ref": "opaque-destination"})
        for _ in range(100):
            record_dead_letter(envelope, "SCHEMA_VALIDATION_FAILED", "schema.v1.invalid")
        dead = DeadLetterEvent.objects.get(pk=envelope.event_id)
        self.assertEqual(dead.retry_count, 100)
        self.assertFalse(hasattr(dead, "payload"))
        self.assertEqual(ProcessedEvent.objects.count(), 0)

    def test_publisher_crash_lease_recovers_without_losing_outbox_row(self):
        envelope = self.envelope()
        with transaction.atomic():
            enqueue_financial_event(envelope)
        claimed = claim_outbox_batch(limit=1, lease_seconds=1)
        self.assertEqual([row.event_id for row in claimed], [envelope.event_id])
        FinancialOutboxEvent.objects.filter(pk=envelope.event_id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.assertEqual(release_expired_claims(), 1)
        reclaimed = claim_outbox_batch(limit=1)
        self.assertEqual(reclaimed[0].attempts, 2)
        mark_outbox_published(envelope.event_id)
        event = FinancialOutboxEvent.objects.get(pk=envelope.event_id)
        self.assertEqual(event.status, FinancialOutboxEvent.Status.PUBLISHED)
        self.assertEqual(FinancialOutboxEvent.objects.count(), 1)

    def test_financial_audit_is_append_only_in_application_and_postgresql(self):
        audit = append_financial_audit(
            action="withdrawal.requested", tenant_ref=uuid.uuid4(),
            correlation_id=uuid.uuid4(), payload={"amount": "10.00", "asset": "USD"},
            subject_ref="withdrawal.opaque-1",
        )
        audit.action = "withdrawal.cancelled"
        with self.assertRaises(TypeError):
            audit.save()
        with self.assertRaises(TypeError):
            audit.delete()
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE financial_audit SET action = %s WHERE id = %s", ["changed", audit.id])
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM financial_audit WHERE id = %s", [audit.id])
        self.assertEqual(FinancialAuditEvent.objects.get(pk=audit.id).action, "withdrawal.requested")
