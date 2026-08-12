from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from financial_boundary.reconciliation import (
    ReconciliationEvidence, Violation, build_reconciliation_incident,
    reconcile_financial_boundary,
)


NOW = datetime(2026, 8, 11, 9, 30, tzinfo=timezone.utc)


def valid_evidence():
    return ReconciliationEvidence(
        application_operations=(
            {"reference": "operation-1", "state": "PENDING", "tenant_ref": "tenant-a", "audit_action": "withdrawal.requested", "outbox_required": True},
            {"reference": "order-1", "state": "ACTIVE", "tenant_ref": "tenant-a", "requires_financial_operation": False},
        ),
        financial_operations=(
            {"reference": "operation-1", "state": "PENDING", "effect_id": "effect-1"},
        ),
        reservations=(
            {"reference": "reservation-1", "order_ref": "order-1", "tenant_ref": "tenant-a", "state": "CONSUMED", "expires_at": (NOW + timedelta(hours=1)).isoformat()},
        ),
        application_settlements=(
            {"reference": "settlement-1", "trade_ref": "trade-1", "reservation_ref": "reservation-1", "state": "COMPLETED", "asset_legs": [{"asset": "USD", "amount": "10.00"}], "fee_components": []},
        ),
        financial_settlements=(
            {"reference": "settlement-1", "trade_ref": "trade-1", "reservation_ref": "reservation-1", "state": "COMPLETED", "asset_legs": [{"asset": "USD", "amount": "10.00"}], "fee_components": []},
        ),
        wallet_projections=(
            {"reference": "wallet-1", "asset": "USD", "total": "100.00", "available": "90.00", "reserved": "10.00", "pending": "0.00", "version": 7},
        ),
        wallet_snapshots=(
            {"reference": "wallet-1", "asset": "USD", "total": "100.00", "available": "90.00", "reserved": "10.00", "pending": "0.00", "version": 7},
        ),
        application_deposits=(
            {"reference": "deposit-1", "state": "CREDITED", "credited_amount": "25.00", "asset": "USD"},
        ),
        financial_deposits=(
            {"reference": "deposit-1", "state": "CREDITED", "credited_amount": "25.00", "asset": "USD"},
        ),
        application_withdrawals=({"reference": "withdrawal-1", "state": "PENDING_APPROVAL"},),
        financial_withdrawals=({"reference": "withdrawal-1", "state": "PENDING_APPROVAL"},),
        application_transfers=({"reference": "transfer-1", "state": "PENDING"},),
        financial_transfers=({"reference": "transfer-1", "state": "PENDING"},),
        outbox=({"reference": "operation-1", "event_id": "outbox-1"},),
        received_events=({"event_id": "event-1"},),
        inbox=({"event_id": "event-1"},),
        audits=({"reference": "operation-1", "action": "withdrawal.requested"},),
    )


class FinancialReconciliationEngineTests(SimpleTestCase):
    def codes(self, evidence):
        return {finding.violation for finding in reconcile_financial_boundary(evidence, as_of=NOW).findings}

    def test_valid_evidence_runs_all_ten_checks_without_false_positive(self):
        report = reconcile_financial_boundary(valid_evidence(), as_of=NOW)
        self.assertTrue(report.activation_ready)
        self.assertEqual(report.critical_count, 0)
        self.assertEqual(set(report.checks_executed), set(Violation))
        self.assertEqual(len(report.checks_executed), 10)
        self.assertEqual(len(report.evidence_hash), 64)

    def test_missing_financial_operation(self):
        evidence = replace(valid_evidence(), financial_operations=())
        self.assertIn(Violation.MISSING_FINANCIAL_OPERATION, self.codes(evidence))

    def test_duplicate_financial_effect(self):
        row = valid_evidence().financial_operations[0]
        evidence = replace(valid_evidence(), financial_operations=(row, dict(row)))
        self.assertIn(Violation.DUPLICATE_FINANCIAL_EFFECT, self.codes(evidence))

    def test_orphan_reservation(self):
        reservation = {**valid_evidence().reservations[0], "order_ref": "unknown-order"}
        self.assertIn(Violation.ORPHAN_RESERVATION, self.codes(replace(valid_evidence(), reservations=(reservation,))))

    def test_reservation_leak(self):
        reservation = {
            **valid_evidence().reservations[0], "state": "ACTIVE",
            "expires_at": (NOW - timedelta(seconds=1)).isoformat(),
        }
        self.assertIn(Violation.RESERVATION_LEAK, self.codes(replace(valid_evidence(), reservations=(reservation,))))

    def test_settlement_mismatch(self):
        settlement = {**valid_evidence().financial_settlements[0], "state": "FAILED"}
        self.assertIn(Violation.SETTLEMENT_MISMATCH, self.codes(replace(valid_evidence(), financial_settlements=(settlement,))))

    def test_wallet_projection_mismatch(self):
        wallet = {**valid_evidence().wallet_snapshots[0], "available": "89.00"}
        self.assertIn(Violation.WALLET_PROJECTION_MISMATCH, self.codes(replace(valid_evidence(), wallet_snapshots=(wallet,))))

    def test_deposit_credit_mismatch(self):
        deposit = {**valid_evidence().financial_deposits[0], "credited_amount": "24.00"}
        self.assertIn(Violation.DEPOSIT_CREDIT_MISMATCH, self.codes(replace(valid_evidence(), financial_deposits=(deposit,))))

    def test_withdrawal_state_mismatch(self):
        withdrawal = {"reference": "withdrawal-1", "state": "COMPLETED"}
        self.assertIn(Violation.WITHDRAWAL_STATE_MISMATCH, self.codes(replace(valid_evidence(), financial_withdrawals=(withdrawal,))))

    def test_transfer_state_mismatch(self):
        transfer = {"reference": "transfer-1", "state": "COMPLETED"}
        self.assertIn(Violation.TRANSFER_STATE_MISMATCH, self.codes(replace(valid_evidence(), financial_transfers=(transfer,))))

    def test_audit_outbox_and_inbox_gaps(self):
        evidence = replace(valid_evidence(), audits=(), outbox=(), inbox=())
        report = reconcile_financial_boundary(evidence, as_of=NOW)
        self.assertIn(Violation.AUDIT_GAP, {finding.violation for finding in report.findings})
        self.assertFalse(report.activation_ready)
        self.assertGreaterEqual(report.critical_count, 2)
        incident = build_reconciliation_incident(
            report, candidate_sha="a" * 40, environment="isolated-test",
        )
        self.assertEqual(incident["type"], "FINANCIAL_RECONCILIATION_FAILURE")
        self.assertEqual(incident["evidence_hash"], report.evidence_hash)
        self.assertNotIn("operation-1", incident["safe_summary"])

    def test_clean_report_cannot_fabricate_incident(self):
        report = reconcile_financial_boundary(valid_evidence(), as_of=NOW)
        with self.assertRaises(ValueError):
            build_reconciliation_incident(report, candidate_sha="a" * 40, environment="isolated-test")

    def test_engine_is_read_only_and_does_not_mutate_inputs(self):
        evidence = valid_evidence()
        before = deepcopy(evidence)
        reconcile_financial_boundary(evidence, as_of=NOW)
        self.assertEqual(evidence, before)

    def test_naive_reconciliation_time_is_rejected(self):
        with self.assertRaises(ValueError):
            reconcile_financial_boundary(valid_evidence(), as_of=datetime(2026, 8, 11))
