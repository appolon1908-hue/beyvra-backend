from datetime import datetime, timedelta, timezone
from decimal import Decimal
from django.test import SimpleTestCase, override_settings

from financial_boundary.contracts import (
    ContractError, DEPOSIT_TRANSITIONS, WITHDRAWAL_TRANSITIONS,
    DepositState, Money, WalletSnapshot, WithdrawalState, assert_transition, canonical_amount,
)
from financial_boundary.providers import DisabledProvider, ProviderAuthorization, ProviderDenied, guard_outbound
from financial_boundary.reconciliation import Violation, compare_records
from financial_boundary.security import WithdrawalSecurityContext, WithdrawalPolicy, assert_separation_of_duties, evaluate_withdrawal
from financial_boundary.metrics import RECONCILIATION_VIOLATIONS, WITHDRAWAL_SECURITY_DENIALS, WITHDRAWAL_STEP_UP_REQUIRED


class MoneyContractTests(SimpleTestCase):
    def test_decimal_string_contract(self):
        self.assertEqual(Money("125.43000000", "USD").amount, "125.43000000")
        for invalid in ("NaN", "Infinity", "-1", "0", "1.000000001"):
            with self.assertRaises(ContractError):
                canonical_amount(invalid)
        with self.assertRaises(ContractError):
            canonical_amount(1.2)

    def test_wallet_snapshot_rejects_negative_or_float(self):
        valid = dict(wallet_id="w", account_ref="a", asset="USD", total="1", available="1", reserved="0", pending="0", as_of="2026-01-01T00:00:00Z", version=1)
        self.assertEqual(WalletSnapshot(**valid).total, "1")
        with self.assertRaises(ContractError): WalletSnapshot(**{**valid, "available": "-1"})
        with self.assertRaises(ContractError): WalletSnapshot(**{**valid, "total": 1.0})


class StateMachineTests(SimpleTestCase):
    def test_deposit_explicit_transitions(self):
        assert_transition(DepositState.CREATED, DepositState.AWAITING_FUNDING, DEPOSIT_TRANSITIONS)
        with self.assertRaises(ContractError):
            assert_transition(DepositState.CREATED, DepositState.CREDITED, DEPOSIT_TRANSITIONS)

    def test_cancel_and_submit_are_mutually_exclusive(self):
        assert_transition(WithdrawalState.QUEUED, WithdrawalState.SUBMITTED, WITHDRAWAL_TRANSITIONS)
        with self.assertRaises(ContractError):
            assert_transition(WithdrawalState.SUBMITTED, WithdrawalState.CANCELLED, WITHDRAWAL_TRANSITIONS)


class SecurityPolicyTests(SimpleTestCase):
    def context(self, now, **changes):
        values = dict(account_active=True, kyc_approved=True, aml_cleared=True, sanctions_clear=True,
                      jurisdiction_supported=True, frozen=False, session_authenticated_at=now,
                      mfa_authenticated_at=now, destination_verified=True)
        values.update(changes)
        return WithdrawalSecurityContext(**values)

    def test_security_gates_fail_closed(self):
        now = datetime(2026, 8, 11, tzinfo=timezone.utc)
        self.assertEqual(evaluate_withdrawal(self.context(now), "10", now=now), "ELIGIBLE")
        self.assertEqual(evaluate_withdrawal(self.context(now, frozen=True), "10", now=now), "WITHDRAWAL_NOT_ALLOWED")
        self.assertEqual(evaluate_withdrawal(self.context(now, mfa_authenticated_at=None), "10", now=now), "STEP_UP_REQUIRED")
        self.assertEqual(evaluate_withdrawal(self.context(now, session_authenticated_at=now-timedelta(hours=1)), "10", now=now), "STEP_UP_REQUIRED")
        self.assertEqual(evaluate_withdrawal(self.context(now, security_changed_at=now), "10", now=now), "SECURITY_CHANGE_COOLDOWN")
        self.assertEqual(evaluate_withdrawal(self.context(now, destination_cooldown_until=now+timedelta(hours=1)), "10", now=now), "DESTINATION_COOLDOWN")
        self.assertEqual(evaluate_withdrawal(self.context(now), "10001", now=now, policy=WithdrawalPolicy(per_transaction_limit=Decimal("10000"))), "REVIEW_REQUIRED")

    def test_security_metrics_have_bounded_reasons_and_step_up_counter(self):
        now = datetime(2026, 8, 11, tzinfo=timezone.utc)
        denial_before = WITHDRAWAL_SECURITY_DENIALS.labels(reason="STEP_UP_REQUIRED")._value.get()
        step_before = WITHDRAWAL_STEP_UP_REQUIRED._value.get()
        self.assertEqual(evaluate_withdrawal(self.context(now, mfa_authenticated_at=None), "10", now=now), "STEP_UP_REQUIRED")
        self.assertEqual(WITHDRAWAL_SECURITY_DENIALS.labels(reason="STEP_UP_REQUIRED")._value.get(), denial_before + 1)
        self.assertEqual(WITHDRAWAL_STEP_UP_REQUIRED._value.get(), step_before + 1)
        self.assertEqual(WITHDRAWAL_SECURITY_DENIALS._labelnames, ("reason",))

    def test_maker_checker(self):
        with self.assertRaises(PermissionError): assert_separation_of_duties("actor", "actor")
        assert_separation_of_duties("actor", "checker")


class ProviderAndReconciliationTests(SimpleTestCase):
    def test_outbound_guard_denies_every_incomplete_authority(self):
        with self.assertRaises(ProviderDenied): guard_outbound(ProviderAuthorization())
        with self.assertRaises(ProviderDenied): DisabledProvider().submit_withdrawal({})

    @override_settings(
        REAL_MONEY_ENABLED=False,
        CUSTODY_PROVIDER_ACTIVATED=False,
        PAYMENT_PROVIDER_ACTIVATED=False,
    )
    def test_outbound_guard_cannot_be_enabled_by_requester_supplied_approvals(self):
        approvals = dict(
            provider_enabled=True, environment_approved=True, operation_allowed=True,
            compliance_approved=True, financial_approved=True, feature_enabled=True,
        )
        with self.assertRaises(ProviderDenied):
            guard_outbound(ProviderAuthorization(provider_type="CUSTODY", **approvals))
        with self.assertRaises(ProviderDenied):
            guard_outbound(ProviderAuthorization(provider_type="PAYMENT", **approvals))

    def test_reconciliation_is_read_only_and_detects_disagreement(self):
        application = [{"reference": "one", "state": "PENDING"}]
        authoritative = [{"reference": "one", "state": "COMPLETED"}, {"reference": "two", "state": "PENDING"}]
        before = repr((application, authoritative))
        findings = compare_records(application, authoritative)
        self.assertEqual(len(findings), 2)
        self.assertIn(("two", Violation.MISSING_FINANCIAL_OPERATION), findings)
        self.assertEqual(repr((application, authoritative)), before)

    def test_reconciliation_detects_duplicate_authoritative_effect(self):
        application = [{"reference": "duplicate", "state": "COMPLETED"}]
        authoritative = [
            {"reference": "duplicate", "state": "COMPLETED"},
            {"reference": "duplicate", "state": "COMPLETED"},
        ]
        before = RECONCILIATION_VIOLATIONS.labels(violation="DUPLICATE_FINANCIAL_EFFECT")._value.get()
        self.assertEqual(compare_records(application, authoritative), [("duplicate", Violation.DUPLICATE_FINANCIAL_EFFECT)])
        self.assertEqual(RECONCILIATION_VIOLATIONS.labels(violation="DUPLICATE_FINANCIAL_EFFECT")._value.get(), before + 1)
        self.assertEqual(RECONCILIATION_VIOLATIONS._labelnames, ("violation",))
