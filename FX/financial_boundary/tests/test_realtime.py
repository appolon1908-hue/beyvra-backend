import uuid

from django.test import TransactionTestCase
from django.utils import timezone

from financial_boundary.eventing import EventContractError
from financial_boundary.models import FinancialProjectionCursor
from financial_boundary.realtime import (
    FINANCIAL_REALTIME_TOPICS, FinancialProjectionEvent, FinancialSequenceConflict,
    apply_projection_event, private_financial_channel, replace_projection_from_snapshot,
)


class FinancialRealtimeProjectionTests(TransactionTestCase):
    def setUp(self):
        self.tenant = uuid.uuid4()
        self.subject = "42"

    def event(self, sequence, **changes):
        values = {
            "event_id": uuid.uuid4(),
            "event_type": "wallet.updated.v1",
            "tenant_ref": self.tenant,
            "subject_ref": self.subject,
            "sequence": sequence,
            "occurred_at": timezone.now(),
            "payload": {"asset": "USD", "available": str(sequence)},
        }
        values.update(changes)
        return FinancialProjectionEvent(**values)

    @staticmethod
    def reduce_wallet(current, payload):
        return {**current, payload["asset"]: {"available": payload["available"]}}

    def test_apply_duplicate_ordering_and_sequence_conflict(self):
        first = self.event(1)
        self.assertEqual(apply_projection_event(first, self.reduce_wallet).status, "APPLIED")
        self.assertEqual(apply_projection_event(first, self.reduce_wallet).status, "DUPLICATE")
        with self.assertRaises(FinancialSequenceConflict):
            apply_projection_event(self.event(1), self.reduce_wallet)
        cursor = FinancialProjectionCursor.objects.get()
        self.assertEqual(cursor.last_sequence, 1)
        self.assertEqual(cursor.projection["USD"]["available"], "1")

    def test_gap_requires_canonical_snapshot_then_stream_resumes(self):
        self.assertEqual(apply_projection_event(self.event(1), self.reduce_wallet).status, "APPLIED")
        gap = apply_projection_event(self.event(3), self.reduce_wallet)
        self.assertEqual(gap.status, "GAP_RECOVERY_REQUIRED")
        self.assertEqual(gap.expected_sequence, 2)
        self.assertEqual(gap.snapshot_endpoint, "/api/v1/wallets/")
        self.assertEqual(FinancialProjectionCursor.objects.get().last_sequence, 1)

        replaced = replace_projection_from_snapshot(
            tenant_ref=self.tenant, subject_ref=self.subject,
            event_type="wallet.updated.v1",
            snapshot={
                "tenant_ref": str(self.tenant), "subject_ref": self.subject,
                "sequence": 3, "version": 7,
                "projection": {"USD": {"available": "3"}},
            },
        )
        self.assertEqual(replaced.status, "SNAPSHOT_REPLACED")
        self.assertEqual(apply_projection_event(self.event(4), self.reduce_wallet).status, "APPLIED")
        cursor = FinancialProjectionCursor.objects.get()
        self.assertEqual(cursor.last_sequence, 4)
        self.assertEqual(cursor.snapshot_version, 7)
        self.assertEqual(cursor.projection["USD"]["available"], "4")

    def test_snapshot_cannot_cross_tenant_or_move_backwards(self):
        apply_projection_event(self.event(1), self.reduce_wallet)
        with self.assertRaises(EventContractError):
            replace_projection_from_snapshot(
                tenant_ref=self.tenant, subject_ref=self.subject,
                event_type="wallet.updated.v1",
                snapshot={
                    "tenant_ref": str(uuid.uuid4()), "subject_ref": self.subject,
                    "sequence": 2, "version": 1, "projection": {},
                },
            )
        replace_projection_from_snapshot(
            tenant_ref=self.tenant, subject_ref=self.subject,
            event_type="wallet.updated.v1",
            snapshot={
                "tenant_ref": str(self.tenant), "subject_ref": self.subject,
                "sequence": 2, "version": 2, "projection": {},
            },
        )
        with self.assertRaises(FinancialSequenceConflict):
            replace_projection_from_snapshot(
                tenant_ref=self.tenant, subject_ref=self.subject,
                event_type="wallet.updated.v1",
                snapshot={
                    "tenant_ref": str(self.tenant), "subject_ref": self.subject,
                    "sequence": 1, "version": 1, "projection": {},
                },
            )

    def test_tenant_cursors_are_isolated(self):
        apply_projection_event(self.event(1), self.reduce_wallet)
        other = self.event(1, tenant_ref=uuid.uuid4())
        apply_projection_event(other, self.reduce_wallet)
        self.assertEqual(FinancialProjectionCursor.objects.count(), 2)

    def test_payload_cannot_override_authenticated_identity(self):
        with self.assertRaises(EventContractError):
            self.event(1, payload={"user_id": "99", "asset": "USD", "available": "1"})
        with self.assertRaises(EventContractError):
            self.event(1, payload={"tenant_ref": str(uuid.uuid4())})

    def test_all_private_topics_have_snapshot_recovery_and_server_channel(self):
        for event_type, endpoint in FINANCIAL_REALTIME_TOPICS.items():
            self.assertTrue(endpoint.startswith("/api/v1/"))
            self.assertEqual(private_financial_channel(event_type, 42), f"{event_type}:42")
