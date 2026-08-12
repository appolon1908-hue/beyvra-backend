from concurrent.futures import ThreadPoolExecutor
import uuid

from django.db import DatabaseError, close_old_connections, transaction
from django.test import TransactionTestCase

from financial_boundary.halts import (
    FINANCIAL_MANAGER, FINANCIAL_OPERATIONS, HaltAuthorizationDenied, HaltDenied,
    HaltTransitionDenied, approve_financial_halt, assert_financial_operation_allowed,
    current_halt_state, request_financial_halt,
)
from financial_boundary.models import (
    FinancialAuditEvent, FinancialHaltApproval, FinancialHaltRequest,
)


class FinancialHaltAuthorityTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant = uuid.uuid4()

    def request(self, state=FinancialHaltRequest.State.WITHDRAWALS_HALTED, actor=11):
        return request_financial_halt(
            tenant_ref=self.tenant, proposed_state=state, requested_by=actor,
            roles={FINANCIAL_OPERATIONS}, reason_code="SECURITY_INCIDENT",
            correlation_id=uuid.uuid4(),
        )

    def approve(self, request, actor=22):
        return approve_financial_halt(
            request_id=request.pk, approved_by=actor, roles={FINANCIAL_MANAGER},
            correlation_id=uuid.uuid4(),
        )

    def test_halt_requires_scoped_maker_and_independent_manager_checker(self):
        with self.assertRaises(HaltAuthorizationDenied):
            request_financial_halt(
                tenant_ref=self.tenant,
                proposed_state=FinancialHaltRequest.State.WITHDRAWALS_HALTED,
                requested_by=11, roles={"support"}, reason_code="SECURITY_INCIDENT",
                correlation_id=uuid.uuid4(),
            )
        request = self.request()
        with self.assertRaises(HaltAuthorizationDenied):
            approve_financial_halt(
                request_id=request.pk, approved_by=11, roles={FINANCIAL_MANAGER},
                correlation_id=uuid.uuid4(),
            )
        with self.assertRaises(HaltAuthorizationDenied):
            approve_financial_halt(
                request_id=request.pk, approved_by=22, roles={"support"},
                correlation_id=uuid.uuid4(),
            )
        approval = self.approve(request)
        self.assertEqual(approval.request_id, request.pk)
        self.assertEqual(current_halt_state(self.tenant), FinancialHaltRequest.State.WITHDRAWALS_HALTED)
        self.assertEqual(FinancialAuditEvent.objects.count(), 2)

    def test_halt_is_tenant_scoped_and_only_reduces_capability(self):
        other_tenant = uuid.uuid4()
        request = self.request()
        self.approve(request)
        with self.assertRaises(HaltDenied):
            assert_financial_operation_allowed(tenant_ref=self.tenant, operation="WITHDRAWAL")
        self.assertEqual(
            assert_financial_operation_allowed(tenant_ref=self.tenant, operation="DEPOSIT"),
            FinancialHaltRequest.State.WITHDRAWALS_HALTED,
        )
        self.assertEqual(
            assert_financial_operation_allowed(tenant_ref=other_tenant, operation="WITHDRAWAL"),
            FinancialHaltRequest.State.ACTIVE,
        )
        incompatible = self.request(FinancialHaltRequest.State.FUNDING_HALTED, actor=33)
        with self.assertRaises(HaltTransitionDenied):
            self.approve(incompatible, actor=44)
        strict = self.request(FinancialHaltRequest.State.ALL_MUTATIONS_HALTED, actor=33)
        self.approve(strict, actor=44)
        for operation in ("DEPOSIT", "WITHDRAWAL", "TRANSFER", "RESERVATION", "SETTLEMENT"):
            with self.assertRaises(HaltDenied):
                assert_financial_operation_allowed(tenant_ref=self.tenant, operation=operation)

    def test_duplicate_approval_is_idempotent_and_history_is_database_immutable(self):
        request = self.request()
        first = self.approve(request)
        duplicate = self.approve(request, actor=23)
        self.assertEqual(first.pk, duplicate.pk)
        self.assertEqual(FinancialHaltApproval.objects.count(), 1)
        self.assertEqual(FinancialAuditEvent.objects.filter(action="financial_halt.approved").count(), 1)
        with self.assertRaises(TypeError):
            request.delete()
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                FinancialHaltRequest.objects.filter(pk=request.pk).update(reason_code="CHANGED")
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                FinancialHaltApproval.objects.filter(pk=first.pk).delete()

    def test_concurrent_checker_approvals_create_one_effect(self):
        request = self.request()

        def approve(actor):
            close_old_connections()
            try:
                return approve_financial_halt(
                    request_id=request.pk, approved_by=actor, roles={FINANCIAL_MANAGER},
                    correlation_id=uuid.uuid4(),
                ).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=20) as executor:
            approvals = list(executor.map(approve, range(100, 200)))
        self.assertEqual(len(set(approvals)), 1)
        self.assertEqual(FinancialHaltApproval.objects.count(), 1)
        self.assertEqual(FinancialAuditEvent.objects.filter(action="financial_halt.approved").count(), 1)
