import json
import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.test import APIClient, APIRequestFactory
from users.models import User

from .errors import BeyvraErrorMapper
from .models import (
    AccountDeletionRequest,
    AccountFreeze,
    AccountSession,
    AuditEvent,
    LegalHold,
    Notification,
    OperatorActionRequest,
    OperatorRole,
    OutboxEvent,
    ProcessedEvent,
    PrivacyExportJob,
    ReportJob,
    SecurityEvent,
    Statement,
    SupportCase,
    SupportCaseEvent,
    TransactionHistoryEntry,
    TradingHalt,
    TradeConfirmation,
)
from .services import (
    approve_operator_request,
    assert_sensitive_mutation_allowed,
    consume_once,
    create_notification,
    csv_safe,
    evaluate_account_risk,
    execute_operator_request,
    issue_session_token_pair,
    issue_simulation_statement,
    notification_group,
    realtime_notification_payload,
    record_delivery_failure,
)
from .tasks import (
    _deliver_notification_outbox_event,
    generate_privacy_export,
    generate_report_artifact,
)


def user(email, phone, brand="tenant-a", staff=False):
    return User.objects.create_user(
        email=email,
        password="safe-test-password",
        phone_number=phone,
        first_name="Test",
        last_name="User",
        brand=brand,
        is_staff=staff,
        is_mfa_enabled=staff,
        two_factor_authentication_enabled=staff,
    )


class FraudAuthorityTests(TestCase):
    def setUp(self):
        self.account = user("account@example.test", "+10000000001")
        self.actor = user("security@example.test", "+10000000002", staff=True)

    def test_risk_decision_is_deterministic(self):
        decision = evaluate_account_risk(
            tenant_id="tenant-a", account=self.account, signals=["NEW_DEVICE"]
        )
        self.assertEqual(decision.decision, "STEP_UP")
        self.assertEqual(decision.reason_codes, ("NEW_DEVICE",))

    def test_freeze_precedes_all_sensitive_authority(self):
        AccountFreeze.objects.create(
            tenant_id="tenant-a",
            account=self.account,
            actor=self.actor,
            level="FULL",
            reason_code="ACCOUNT_REVIEW_REQUIRED",
        )
        self.assertEqual(
            evaluate_account_risk(
                tenant_id="tenant-a", account=self.account, signals=[]
            ).decision,
            "DENY",
        )
        with self.assertRaisesRegex(PermissionError, "ACCOUNT_FROZEN"):
            assert_sensitive_mutation_allowed(
                tenant_id="tenant-a", account=self.account, action="trading"
            )

    def test_partial_freeze_blocks_withdrawal(self):
        AccountFreeze.objects.create(
            tenant_id="tenant-a",
            account=self.account,
            actor=self.actor,
            level="PARTIAL",
            reason_code="HIGH_RISK_ACTION",
        )
        with self.assertRaises(PermissionError):
            assert_sensitive_mutation_allowed(
                tenant_id="tenant-a", account=self.account, action="withdrawal"
            )

    def test_active_trading_halt_precedes_account_trading_authority(self):
        TradingHalt.objects.create(
            tenant_id="tenant-a",
            reason="synthetic market integrity incident",
            activated_by=self.actor,
        )
        with self.assertRaisesRegex(PermissionError, "TRADING_HALTED"):
            assert_sensitive_mutation_allowed(
                tenant_id="tenant-a", account=self.account, action="trading"
            )


class TenantIsolationApiTests(TestCase):
    def setUp(self):
        self.a = user("a@example.test", "+10000000011", "a")
        self.b = user("b@example.test", "+10000000012", "b")
        self.client = APIClient()

    def test_support_case_idor_returns_safe_not_found(self):
        case = SupportCase.objects.create(
            tenant_id="b", account=self.b, category="OTHER", safe_summary="private"
        )
        self.client.force_authenticate(self.a)
        response = self.client.get(f"/api/v1/support/cases/{case.pk}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "error": {"code": "RESOURCE_NOT_FOUND", "message": "Resource not found.", "details": {}},
                "code": "RESOURCE_NOT_FOUND",
                "message": "Resource not found.",
                "details": {},
                "instance": f"/api/v1/support/cases/{case.pk}",
                "request_id": "",
            },
        )

    def test_internal_notes_never_reach_customer_timeline(self):
        case = SupportCase.objects.create(
            tenant_id="a", account=self.a, category="SECURITY", safe_summary="help"
        )
        SupportCaseEvent.objects.create(
            tenant_id="a",
            account=self.a,
            case=case,
            event_type="INTERNAL_NOTE",
            visibility="INTERNAL_NOTE",
            body_safe="risk model detail",
            actor=self.a,
        )
        SupportCaseEvent.objects.create(
            tenant_id="a",
            account=self.a,
            case=case,
            event_type="MESSAGE_ADDED",
            visibility="CUSTOMER_VISIBLE_MESSAGE",
            body_safe="public update",
            actor=self.a,
        )
        self.client.force_authenticate(self.a)
        body = self.client.get(f"/api/v1/support/cases/{case.pk}").json()
        self.assertEqual(
            [event["body_safe"] for event in body["timeline"]], ["public update"]
        )

    def test_notification_idor_cannot_mark_read(self):
        notification = Notification.objects.create(
            tenant_id="b",
            account=self.b,
            type="NEW_DEVICE",
            category="SECURITY",
            channel="IN_APP",
            template_version="1",
            dedup_key="x",
        )
        self.client.force_authenticate(self.a)
        response = self.client.post(f"/api/v1/notifications/{notification.pk}/read")
        self.assertEqual(response.status_code, 404)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)

    def test_reports_are_account_scoped_and_precise(self):
        TransactionHistoryEntry.objects.create(
            tenant_id="a",
            account=self.a,
            type="TRADE",
            asset="BTC",
            amount=Decimal("0.123456789012"),
            fee=Decimal("0.000000000001"),
            status="SETTLED",
            occurred_at=timezone.now(),
            source_ref="sim-1",
        )
        TransactionHistoryEntry.objects.create(
            tenant_id="b",
            account=self.b,
            type="TRADE",
            asset="BTC",
            amount=1,
            status="SETTLED",
            occurred_at=timezone.now(),
            source_ref="sim-2",
        )
        self.client.force_authenticate(self.a)
        results = self.client.get("/api/v1/reports/transactions").json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["amount"], "0.123456789012000000")
        self.assertTrue(results[0]["simulation"])

    def test_report_routes_enforce_canonical_history_type(self):
        now = timezone.now()
        for history_type in ("TRADE", "FEE"):
            TransactionHistoryEntry.objects.create(
                tenant_id="a",
                account=self.a,
                type=history_type,
                asset="BTC",
                amount=Decimal("1"),
                fee=Decimal("0.01"),
                status="SETTLED",
                occurred_at=now,
                source_ref=f"sim-{history_type.lower()}",
            )
        self.client.force_authenticate(self.a)
        trades = self.client.get("/api/v1/reports/trades").json()["results"]
        fees = self.client.get("/api/v1/reports/fees").json()["results"]
        self.assertEqual([entry["type"] for entry in trades], ["TRADE"])
        self.assertEqual([entry["type"] for entry in fees], ["FEE"])

    def test_report_date_range_is_validated_safely(self):
        self.client.force_authenticate(self.a)
        response = self.client.get(
            "/api/v1/reports/activity",
            {"date_from": "2026-08-02T00:00:00Z", "date_to": "2026-08-01T00:00:00Z"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_REQUEST")

    def test_privacy_deletion_is_idempotent_and_hold_safe(self):
        LegalHold.objects.create(
            tenant_id="a", account=self.a, reason="fixture", created_by=self.a
        )
        self.client.force_authenticate(self.a)
        headers = {"HTTP_IDEMPOTENCY_KEY": "delete-1"}
        first = self.client.post(
            "/api/v1/privacy/deletion-requests", {}, format="json", **headers
        )
        second = self.client.post(
            "/api/v1/privacy/deletion-requests", {}, format="json", **headers
        )
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertTrue(first.json()["blocked_by_legal_hold"])
        self.assertEqual(AccountDeletionRequest.objects.count(), 1)

    def test_revoke_others_does_not_revoke_current_session(self):
        current = AccountSession.objects.create(
            tenant_id="a",
            account=self.a,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        other = AccountSession.objects.create(
            tenant_id="a",
            account=self.a,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_authenticate(self.a)
        response = self.client.post(
            "/api/v1/security/sessions/revoke-others",
            {"current_session_id": str(current.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        current.refresh_from_db()
        other.refresh_from_db()
        self.assertIsNone(current.revoked_at)
        self.assertIsNotNone(other.revoked_at)


class SessionBindingTests(TestCase):
    def setUp(self):
        self.account = user("bound@example.test", "+10000000019")

    def test_issued_token_is_bound_to_revocable_session(self):
        request = APIRequestFactory().post(
            "/api/users/login/", HTTP_USER_AGENT="safe-browser/1.0"
        )
        credentials = issue_session_token_pair(
            user=self.account, request=request, mfa_verified=False
        )
        session = credentials["session"]
        self.assertEqual(session.auth_strength, "PASSWORD")
        self.assertEqual(SecurityEvent.objects.filter(account=self.account).count(), 3)
        self.assertTrue(
            Notification.objects.filter(
                account=self.account, type="NEW_DEVICE"
            ).exists()
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {credentials['access']}")
        self.assertEqual(client.get("/api/v1/security/sessions").status_code, 200)
        session.revoked_at = timezone.now()
        session.save(update_fields=("revoked_at",))
        self.assertEqual(client.get("/api/v1/security/sessions").status_code, 401)


class NotificationAuthorityTests(TestCase):
    def setUp(self):
        self.account = user("notify@example.test", "+10000000021")

    def test_deduplication_has_one_business_effect(self):
        first, created = create_notification(
            tenant_id="tenant-a",
            account=self.account,
            type="NEW_DEVICE",
            category="SECURITY",
            channel="IN_APP",
            template_version="1",
            payload_safe={"action": "review"},
            dedup_key="device:1",
        )
        second, duplicate_created = create_notification(
            tenant_id="tenant-a",
            account=self.account,
            type="NEW_DEVICE",
            category="SECURITY",
            channel="IN_APP",
            template_version="1",
            payload_safe={"action": "review"},
            dedup_key="device:1",
        )
        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(first.pk, second.pk)

    def test_inbox_consumes_once(self):
        effects = []
        event_id = uuid.uuid4()
        self.assertTrue(
            consume_once(
                event_id=event_id, consumer="test", effect=lambda: effects.append(1)
            )
        )
        self.assertFalse(
            consume_once(
                event_id=event_id, consumer="test", effect=lambda: effects.append(2)
            )
        )
        self.assertEqual(effects, [1])

    def test_retry_is_bounded_and_dead_letters(self):
        notification, _ = create_notification(
            tenant_id="tenant-a",
            account=self.account,
            type="PASSWORD_CHANGED",
            category="SECURITY",
            channel="EMAIL",
            template_version="1",
            payload_safe={},
            dedup_key="password:1",
        )
        for _ in range(4):
            self.assertEqual(
                record_delivery_failure(
                    notification, transient=True, reason_safe="temporary"
                ),
                "QUEUED",
            )
        self.assertEqual(
            record_delivery_failure(
                notification, transient=True, reason_safe="temporary"
            ),
            "FAILED",
        )
        self.assertEqual(notification.attempts, 5)

    @patch("operations.tasks.publish_realtime_notification")
    def test_in_app_outbox_delivery_is_idempotent(self, publish):
        notification, _ = create_notification(
            tenant_id="tenant-a",
            account=self.account,
            type="NEW_DEVICE",
            category="SECURITY",
            channel="IN_APP",
            template_version="1",
            payload_safe={"action": "review_sessions"},
            dedup_key="outbox-in-app-1",
        )
        event = OutboxEvent.objects.get(
            topic="notification.created",
            payload_safe__notification_id=str(notification.pk),
        )
        self.assertEqual(_deliver_notification_outbox_event(event.pk), "PUBLISHED")
        self.assertEqual(
            _deliver_notification_outbox_event(event.pk), "ALREADY_PUBLISHED"
        )
        notification.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(notification.status, "SENT")
        self.assertIsNotNone(notification.sent_at)
        self.assertIsNotNone(event.published_at)
        self.assertEqual(publish.call_count, 1)
        self.assertEqual(
            ProcessedEvent.objects.filter(
                event_id=event.pk,
                consumer="operations.notification.delivery.v1",
            ).count(),
            1,
        )

    def test_external_channel_is_dead_lettered_without_delivery_claim(self):
        notification, _ = create_notification(
            tenant_id="tenant-a",
            account=self.account,
            type="PASSWORD_CHANGED",
            category="SECURITY",
            channel="EMAIL",
            template_version="1",
            payload_safe={"action": "review_sessions"},
            dedup_key="outbox-email-disabled-1",
        )
        event = OutboxEvent.objects.get(
            topic="notification.created",
            payload_safe__notification_id=str(notification.pk),
        )
        self.assertEqual(_deliver_notification_outbox_event(event.pk), "PUBLISHED")
        notification.refresh_from_db()
        self.assertEqual(notification.status, "FAILED")
        self.assertIsNone(notification.sent_at)
        self.assertIsNone(notification.delivered_at)
        self.assertTrue(
            OutboxEvent.objects.filter(
                topic="notification.dead_letter",
                payload_safe__notification_id=str(notification.pk),
            ).exists()
        )


class OperatorAuthorityTests(TestCase):
    def setUp(self):
        self.maker = user("maker@example.test", "+10000000031", staff=True)
        self.checker = user("checker@example.test", "+10000000032", staff=True)
        OperatorRole.objects.create(
            user=self.checker, tenant_id="tenant-a", role="security_manager"
        )

    def action(self):
        return OperatorActionRequest.objects.create(
            tenant_id="tenant-a",
            action_type="UNFREEZE",
            target_ref="account:1",
            requested_by=self.maker,
            reason="reviewed evidence",
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def test_self_approval_is_forbidden(self):
        action = self.action()
        with self.assertRaisesRegex(PermissionError, "SELF_APPROVAL_FORBIDDEN"):
            approve_operator_request(
                request_id=action.pk,
                tenant_id="tenant-a",
                approver=self.maker,
                approver_roles={"security_manager"},
            )

    def test_operator_workflow_commands_replay_exactly_once(self):
        OperatorRole.objects.create(
            user=self.maker, tenant_id="tenant-a", role="security_manager"
        )
        freeze = AccountFreeze.objects.create(
            tenant_id="tenant-a", account=self.maker, actor=self.checker,
            level="FULL", reason_code="ACCOUNT_REVIEW_REQUIRED",
        )
        client = APIClient(); client.force_authenticate(self.checker)
        create_headers = {
            "HTTP_X_BEYVRA_TENANT": "tenant-a", "HTTP_IDEMPOTENCY_KEY": "action-create-test",
            "HTTP_X_REQUEST_ID": "fe9e2361-87ad-4bd5-86d6-85859169a010",
        }
        payload = {"action_type": "UNFREEZE", "target_ref": f"account:{self.maker.pk}", "reason": "review complete"}
        created = client.post("/api/internal/v1/actions", payload, format="json", **create_headers)
        replay = client.post("/api/internal/v1/actions", payload, format="json", **create_headers)
        self.assertEqual(created.status_code, 201); self.assertEqual(replay.data, created.data)
        self.assertEqual(OperatorActionRequest.objects.filter(target_ref=f"account:{self.maker.pk}").count(), 1)

        action_id = created.data["request_id"]
        client.force_authenticate(self.maker)
        approve_headers = {
            "HTTP_X_BEYVRA_TENANT": "tenant-a", "HTTP_IDEMPOTENCY_KEY": "action-approve-test",
            "HTTP_X_REQUEST_ID": "fe9e2361-87ad-4bd5-86d6-85859169a011", "HTTP_IF_MATCH": "PENDING",
        }
        approved = client.post(f"/api/internal/v1/actions/{action_id}/approve", {}, format="json", **approve_headers)
        approval_replay = client.post(f"/api/internal/v1/actions/{action_id}/approve", {}, format="json", **approve_headers)
        self.assertEqual(approved.status_code, 200); self.assertEqual(approval_replay.data, approved.data)

        execute_headers = {
            "HTTP_X_BEYVRA_TENANT": "tenant-a", "HTTP_IDEMPOTENCY_KEY": "action-execute-test",
            "HTTP_X_REQUEST_ID": "fe9e2361-87ad-4bd5-86d6-85859169a012", "HTTP_IF_MATCH": "APPROVED",
        }
        executed = client.post(f"/api/internal/v1/actions/{action_id}/execute", {}, format="json", **execute_headers)
        execution_replay = client.post(f"/api/internal/v1/actions/{action_id}/execute", {}, format="json", **execute_headers)
        self.assertEqual(executed.status_code, 200); self.assertEqual(execution_replay.data, executed.data)
        freeze.refresh_from_db(); self.assertIsNotNone(freeze.released_at)
        self.assertEqual(AuditEvent.objects.filter(request_id=action_id, action="ACCOUNT_UNFROZEN").count(), 1)

    def test_independent_manager_can_approve_once(self):
        action = self.action()
        approved = approve_operator_request(
            request_id=action.pk,
            tenant_id="tenant-a",
            approver=self.checker,
            approver_roles={"security_manager"},
        )
        self.assertEqual(approved.status, "APPROVED")
        with self.assertRaises(PermissionError):
            approve_operator_request(
                request_id=action.pk,
                tenant_id="tenant-a",
                approver=self.checker,
                approver_roles={"security_manager"},
            )

    def test_action_approval_is_tenant_bound(self):
        action = self.action()
        with self.assertRaises(OperatorActionRequest.DoesNotExist):
            approve_operator_request(
                request_id=action.pk,
                tenant_id="tenant-b",
                approver=self.checker,
                approver_roles={"security_manager"},
            )
        action.refresh_from_db()
        self.assertEqual(action.status, "PENDING")

    def test_action_approval_requires_the_matching_domain_manager(self):
        action = self.action()
        with self.assertRaisesRegex(PermissionError, "INSUFFICIENT_ROLE"):
            approve_operator_request(
                request_id=action.pk,
                tenant_id="tenant-a",
                approver=self.checker,
                approver_roles={"support_manager", "compliance_manager"},
            )
        action.refresh_from_db()
        self.assertEqual(action.status, "PENDING")

    def test_approved_unfreeze_executes_once_with_audit_hashes(self):
        freeze = AccountFreeze.objects.create(
            tenant_id="tenant-a",
            account=self.maker,
            actor=self.checker,
            level="FULL",
            reason_code="ACCOUNT_REVIEW_REQUIRED",
        )
        action = OperatorActionRequest.objects.create(
            tenant_id="tenant-a",
            action_type="UNFREEZE",
            target_ref=f"account:{self.maker.pk}",
            requested_by=self.maker,
            reason="independent review complete",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        approve_operator_request(
            request_id=action.pk,
            tenant_id="tenant-a",
            approver=self.checker,
            approver_roles={"security_manager"},
        )
        executed = execute_operator_request(
            request_id=action.pk,
            tenant_id="tenant-a",
            executor=self.checker,
            executor_roles={"security_manager"},
        )
        self.assertEqual(executed.status, "EXECUTED")
        freeze.refresh_from_db()
        self.assertIsNotNone(freeze.released_at)
        audit = AuditEvent.objects.get(request_id=action.pk, action="ACCOUNT_UNFROZEN")
        self.assertEqual(len(audit.before_state_hash), 64)
        self.assertEqual(len(audit.after_state_hash), 64)
        with self.assertRaises(PermissionError):
            execute_operator_request(
                request_id=action.pk,
                tenant_id="tenant-a",
                executor=self.checker,
                executor_roles={"security_manager"},
            )

    def test_provider_activation_cannot_execute_in_this_service(self):
        action = OperatorActionRequest.objects.create(
            tenant_id="tenant-a",
            action_type="PROVIDER_ACTIVATION",
            target_ref="provider:future",
            requested_by=self.maker,
            reason="fixture only",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        approve_operator_request(
            request_id=action.pk,
            tenant_id="tenant-a",
            approver=self.checker,
            approver_roles={"operations_manager"},
        )
        with self.assertRaisesRegex(PermissionError, "EXTERNAL_AUTHORITY_REQUIRED"):
            execute_operator_request(
                request_id=action.pk,
                tenant_id="tenant-a",
                executor=self.checker,
                executor_roles={"operations_manager"},
            )
        action.refresh_from_db()
        self.assertEqual(action.status, "APPROVED")

    def test_audit_is_immutable(self):
        audit = AuditEvent.objects.create(
            tenant_id="tenant-a", actor=self.checker, action="TEST", target="safe"
        )
        audit.reason = "mutated"
        with self.assertRaises(ValidationError):
            audit.save()
        with self.assertRaises(ValidationError):
            audit.delete()

    def test_postgresql_rejects_bulk_audit_mutation(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL trigger certification")
        audit = AuditEvent.objects.create(
            tenant_id="tenant-a", actor=self.checker, action="TEST", target="safe"
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditEvent.objects.filter(pk=audit.pk).update(reason="bypass")
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditEvent.objects.filter(pk=audit.pk).delete()

    def test_statement_is_immutable_after_issue(self):
        statement = Statement.objects.create(
            tenant_id="tenant-a",
            account=self.maker,
            period_start=timezone.now() - timedelta(days=30),
            period_end=timezone.now(),
            simulation=True,
            reconciliation_passed=True,
        )
        statement.correction_reason = "silent replacement"
        with self.assertRaises(ValidationError):
            statement.save()
        with self.assertRaises(ValidationError):
            statement.delete()

    def test_operator_action_request_uses_governed_mutable_state(self):
        action = self.action()
        approve_operator_request(
            request_id=action.pk,
            tenant_id="tenant-a",
            approver=self.checker,
            approver_roles={"security_manager"},
        )
        action.refresh_from_db()
        self.assertEqual(action.status, "APPROVED")
        with self.assertRaises(ValidationError):
            action.delete()

    def test_support_agent_can_escalate_but_customer_cannot_use_operator_api(self):
        account = user("supported@example.test", "+10000000033")
        support = user("support@example.test", "+10000000034", staff=True)
        OperatorRole.objects.create(
            user=support, tenant_id="tenant-a", role="support_agent"
        )
        case = SupportCase.objects.create(
            tenant_id="tenant-a",
            account=account,
            category="SECURITY",
            safe_summary="help",
        )
        client = APIClient()
        client.force_authenticate(account)
        self.assertEqual(
            client.post(
                f"/api/internal/v1/support/cases/{case.pk}/events", {}
            ).status_code,
            403,
        )
        client.force_authenticate(support)
        response = client.post(
            f"/api/internal/v1/support/cases/{case.pk}/events",
            {
                "event_type": "ESCALATED",
                "team": "SECURITY",
                "reason": "security review",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        case.refresh_from_db()
        self.assertEqual((case.status, case.assigned_team), ("ESCALATED", "SECURITY"))

    def test_support_assignment_resolution_and_reopen_update_authoritative_case(self):
        account = user("case-account@example.test", "+10000000039")
        manager = user("case-manager@example.test", "+10000000040", staff=True)
        assignee = user("case-assignee@example.test", "+10000000045", staff=True)
        OperatorRole.objects.create(
            user=manager, tenant_id="tenant-a", role="support_manager"
        )
        OperatorRole.objects.create(
            user=assignee, tenant_id="tenant-a", role="support_agent"
        )
        case = SupportCase.objects.create(
            tenant_id="tenant-a",
            account=account,
            category="TECHNICAL",
            safe_summary="synthetic support state test",
        )
        client = APIClient()
        client.force_authenticate(manager)
        endpoint = f"/api/internal/v1/support/cases/{case.pk}/events"
        self.assertEqual(
            client.post(
                endpoint,
                {"event_type": "ASSIGNED", "assigned_to": assignee.pk},
                format="json",
            ).status_code,
            201,
        )
        self.assertEqual(
            client.post(endpoint, {"event_type": "RESOLVED"}, format="json").status_code,
            201,
        )
        case.refresh_from_db()
        self.assertEqual(case.assigned_to, assignee)
        self.assertEqual(case.status, "RESOLVED")
        self.assertIsNotNone(case.resolved_at)
        self.assertEqual(
            client.post(endpoint, {"event_type": "REOPENED"}, format="json").status_code,
            201,
        )
        case.refresh_from_db()
        self.assertEqual(case.status, "OPEN")
        self.assertIsNone(case.resolved_at)

    def test_wrong_tenant_account_cannot_be_frozen(self):
        outsider = user("outsider@example.test", "+10000000035", brand="tenant-b")
        client = APIClient()
        client.force_authenticate(self.checker)
        response = client.post(
            f"/api/internal/v1/accounts/{outsider.pk}/freeze",
            {"level": "FULL"},
            format="json",
            HTTP_X_BEYVRA_TENANT="tenant-a",
            HTTP_IDEMPOTENCY_KEY="freeze-wrong-tenant",
            HTTP_X_REQUEST_ID="fe9e2361-87ad-4bd5-86d6-85859169a001",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(AccountFreeze.objects.filter(account=outsider).exists())

    def test_wrong_tenant_operator_cannot_approve_action_by_id(self):
        action = self.action()
        outsider = user(
            "tenant-b-security@example.test",
            "+10000000046",
            brand="tenant-b",
            staff=True,
        )
        OperatorRole.objects.create(
            user=outsider, tenant_id="tenant-b", role="security_manager"
        )
        client = APIClient()
        client.force_authenticate(outsider)
        response = client.post(
            f"/api/internal/v1/actions/{action.pk}/approve",
            HTTP_X_BEYVRA_TENANT="tenant-b",
            HTTP_IDEMPOTENCY_KEY="approve-wrong-tenant",
            HTTP_X_REQUEST_ID="fe9e2361-87ad-4bd5-86d6-85859169a002",
            HTTP_IF_MATCH="PENDING",
        )
        self.assertEqual(response.status_code, 403)
        action.refresh_from_db()
        self.assertEqual(action.status, "PENDING")

    def test_support_manager_cannot_request_security_action_or_create_legal_hold(self):
        support = user(
            "support-manager@example.test", "+10000000047", staff=True
        )
        OperatorRole.objects.create(
            user=support, tenant_id="tenant-a", role="support_manager"
        )
        client = APIClient()
        client.force_authenticate(support)
        request_response = client.post(
            "/api/internal/v1/actions",
            {
                "action_type": "UNFREEZE",
                "target_ref": f"account:{self.maker.pk}",
                "reason": "not a support authority",
            },
            format="json",
            HTTP_X_BEYVRA_TENANT="tenant-a",
            HTTP_IDEMPOTENCY_KEY="unauthorized-action",
            HTTP_X_REQUEST_ID="fe9e2361-87ad-4bd5-86d6-85859169a003",
        )
        hold_response = client.post(
            f"/api/internal/v1/accounts/{self.maker.pk}/legal-holds",
            {"reason": "not a support authority"},
            format="json",
            HTTP_X_BEYVRA_TENANT="tenant-a",
            HTTP_IDEMPOTENCY_KEY="unauthorized-hold",
            HTTP_X_REQUEST_ID="fe9e2361-87ad-4bd5-86d6-85859169a004",
        )
        self.assertEqual(request_response.status_code, 403)
        self.assertEqual(hold_response.status_code, 403)
        self.assertFalse(LegalHold.objects.filter(account=self.maker).exists())

    def test_safe_account_summary_is_tenant_bound_and_contains_no_direct_pii(self):
        client = APIClient()
        client.force_authenticate(self.checker)
        response = client.get(
            f"/api/internal/v1/accounts/{self.maker.pk}/summary",
            HTTP_X_BEYVRA_TENANT="tenant-a",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["account_ref"], str(self.maker.pk))
        serialized = json.dumps(response.data).lower()
        self.assertNotIn(self.maker.email.lower(), serialized)
        self.assertNotIn("phone_number", serialized)
        self.assertNotIn("password", serialized)
        outsider = user(
            "summary-outsider@example.test", "+10000000048", brand="tenant-b"
        )
        self.assertEqual(
            client.get(
                f"/api/internal/v1/accounts/{outsider.pk}/summary",
                HTTP_X_BEYVRA_TENANT="tenant-a",
            ).status_code,
            404,
        )

    def test_support_audit_timeline_is_filtered_by_domain(self):
        support = user("audit-support@example.test", "+10000000049", staff=True)
        OperatorRole.objects.create(
            user=support, tenant_id="tenant-a", role="support_viewer"
        )
        AuditEvent.objects.create(
            tenant_id="tenant-a",
            actor=self.checker,
            action="SUPPORT_CASE_CREATED",
            target="case:safe",
        )
        AuditEvent.objects.create(
            tenant_id="tenant-a",
            actor=self.checker,
            action="ACCOUNT_FROZEN",
            target="account:safe",
        )
        client = APIClient()
        client.force_authenticate(support)
        response = client.get(
            "/api/internal/v1/audit-timeline",
            HTTP_X_BEYVRA_TENANT="tenant-a",
        )
        self.assertEqual(response.status_code, 200)
        actions = {row["action"] for row in response.data}
        self.assertIn("SUPPORT_CASE_CREATED", actions)
        self.assertNotIn("ACCOUNT_FROZEN", actions)

    def test_emergency_halt_release_requires_independent_operations_authority(self):
        maker = user("halt-maker@example.test", "+10000000050", staff=True)
        checker = user("halt-checker@example.test", "+10000000051", staff=True)
        OperatorRole.objects.create(
            user=maker, tenant_id="tenant-a", role="operations_manager"
        )
        OperatorRole.objects.create(
            user=checker, tenant_id="tenant-a", role="operations_manager"
        )
        client = APIClient()
        client.force_authenticate(maker)
        halted = client.post(
            "/api/internal/v1/trading/halt",
            {"reason": "synthetic incident fixture"},
            format="json",
            HTTP_X_BEYVRA_TENANT="tenant-a",
            HTTP_IDEMPOTENCY_KEY="halt-fixture",
            HTTP_X_REQUEST_ID="fe9e2361-87ad-4bd5-86d6-85859169a005",
        )
        self.assertEqual(halted.status_code, 201)
        action = OperatorActionRequest.objects.create(
            tenant_id="tenant-a",
            action_type="KILL_SWITCH_RELEASE",
            target_ref=f"trading_halt:{halted.data['halt_id']}",
            requested_by=maker,
            reason="independent recovery review",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        approve_operator_request(
            request_id=action.pk,
            tenant_id="tenant-a",
            approver=checker,
            approver_roles={"operations_manager"},
        )
        execute_operator_request(
            request_id=action.pk,
            tenant_id="tenant-a",
            executor=checker,
            executor_roles={"operations_manager"},
        )
        halt = TradingHalt.objects.get(pk=halted.data["halt_id"])
        self.assertIsNotNone(halt.released_at)
        self.assertEqual(halt.released_by, checker)

    def test_legal_hold_release_requires_independent_compliance_authority(self):
        maker = user("hold-maker@example.test", "+10000000052", staff=True)
        checker = user("hold-checker@example.test", "+10000000053", staff=True)
        hold = LegalHold.objects.create(
            tenant_id="tenant-a",
            account=self.maker,
            reason="synthetic legal hold fixture",
            created_by=maker,
        )
        action = OperatorActionRequest.objects.create(
            tenant_id="tenant-a",
            action_type="LEGAL_HOLD_RELEASE",
            target_ref=f"legal_hold:{hold.pk}",
            requested_by=maker,
            reason="independent release review",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        approve_operator_request(
            request_id=action.pk,
            tenant_id="tenant-a",
            approver=checker,
            approver_roles={"compliance_manager"},
        )
        execute_operator_request(
            request_id=action.pk,
            tenant_id="tenant-a",
            executor=checker,
            executor_roles={"compliance_manager"},
        )
        hold.refresh_from_db()
        self.assertFalse(hold.active)
        self.assertEqual(hold.released_by, checker)


class ReportingAuthorityTests(TestCase):
    def setUp(self):
        self.account = user("statement-account@example.test", "+10000000054")
        self.operator = user("financial-manager@example.test", "+10000000055", staff=True)
        OperatorRole.objects.create(
            user=self.operator, tenant_id="tenant-a", role="financial_manager"
        )

    def test_simulation_statement_correction_creates_new_immutable_version(self):
        start = timezone.now() - timedelta(days=30)
        end = timezone.now()
        original = issue_simulation_statement(
            tenant_id="tenant-a",
            account=self.account,
            period_start=start,
            period_end=end,
            actor=self.operator,
        )
        correction = issue_simulation_statement(
            tenant_id="tenant-a",
            account=self.account,
            period_start=start,
            period_end=end,
            actor=self.operator,
            supersedes=original,
            reason="synthetic correction fixture",
        )
        self.assertEqual(correction.statement_id, original.statement_id)
        self.assertEqual(correction.version, 2)
        self.assertEqual(correction.supersedes, original)
        self.assertTrue(correction.simulation)
        self.assertTrue(correction.reconciliation_passed)
        self.assertEqual(Statement.objects.count(), 2)

    def test_real_history_prevents_local_statement_authority(self):
        TransactionHistoryEntry.objects.create(
            tenant_id="tenant-a",
            account=self.account,
            type="SETTLEMENT",
            asset="USD",
            amount=Decimal("1.00"),
            status="SETTLED",
            occurred_at=timezone.now(),
            source_ref="financial-authority-fixture",
            simulation=False,
        )
        with self.assertRaisesRegex(
            PermissionError, "FINANCIAL_SERVICE_AUTHORITY_REQUIRED"
        ):
            issue_simulation_statement(
                tenant_id="tenant-a",
                account=self.account,
                period_start=timezone.now() - timedelta(days=1),
                period_end=timezone.now() + timedelta(seconds=1),
                actor=self.operator,
            )

    def test_trade_confirmation_api_is_owner_and_tenant_scoped(self):
        confirmation = TradeConfirmation.objects.create(
            tenant_id="tenant-a",
            account=self.account,
            order_ref="demo-order-1",
            instrument="BTC-USD",
            side="BUY",
            quantity=Decimal("0.010000000000000000"),
            price=Decimal("25000.000000000000000000"),
            fee=Decimal("1.250000000000000000"),
            executed_at=timezone.now(),
            simulation=True,
        )
        client = APIClient()
        client.force_authenticate(self.account)
        response = client.get("/api/v1/reports/trade-confirmations")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["trade_id"], str(confirmation.pk))
        outsider = user(
            "confirmation-outsider@example.test", "+10000000056", brand="tenant-b"
        )
        client.force_authenticate(outsider)
        self.assertEqual(
            client.get("/api/v1/reports/trade-confirmations").data["count"], 0
        )

    def test_default_tenant_operator_can_target_null_brand_account(self):
        account = user("default-account@example.test", "+10000000037", brand=None)
        operator = user(
            "default-security@example.test", "+10000000038", brand=None, staff=True
        )
        OperatorRole.objects.create(
            user=operator, tenant_id="default", role="security_manager"
        )
        client = APIClient()
        client.force_authenticate(operator)
        response = client.post(
            f"/api/internal/v1/accounts/{account.pk}/freeze",
            {"level": "FULL", "reason_code": "ACCOUNT_REVIEW_REQUIRED"},
            format="json",
            HTTP_X_BEYVRA_TENANT="default",
            HTTP_IDEMPOTENCY_KEY="freeze-default",
            HTTP_X_REQUEST_ID="fe9e2361-87ad-4bd5-86d6-85859169a006",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            AccountFreeze.objects.filter(
                tenant_id="default", account=account, released_at__isnull=True
            ).exists()
        )

    def test_operator_without_mfa_cannot_access_internal_api(self):
        operator = user("no-mfa@example.test", "+10000000036", staff=False)
        operator.is_staff = True
        operator.save(update_fields=("is_staff",))
        OperatorRole.objects.create(
            user=operator, tenant_id="tenant-a", role="support_viewer"
        )
        client = APIClient()
        client.force_authenticate(operator)
        self.assertEqual(client.get("/api/internal/v1/safety-flags").status_code, 403)


class ExportSafetyTests(TestCase):
    def test_csv_formula_prefixes_are_neutralized(self):
        for prefix in "=+-@":
            self.assertEqual(csv_safe(prefix + "cmd"), "'" + prefix + "cmd")
        self.assertEqual(csv_safe("normal"), "normal")

    def test_real_money_error_is_feature_disabled_without_internal_detail(self):
        response = BeyvraErrorMapper(
            DRFValidationError("Real-money trading is disabled in this environment."),
            {},
        )
        self.assertEqual(
            response.data,
            {
                "error": {"code": "FEATURE_DISABLED", "message": "This feature is currently unavailable.", "details": {}},
                "code": "FEATURE_DISABLED",
                "message": "This feature is currently unavailable.",
                "details": {},
                "instance": "",
                "request_id": "",
            },
        )

    def test_cache_outage_maps_to_safe_service_unavailable(self):
        CacheConnectionError = type(
            "ConnectionError", (Exception,), {"__module__": "redis.exceptions"}
        )
        response = BeyvraErrorMapper(CacheConnectionError("sensitive endpoint"), {})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.data,
            {
                "error": {"code": "SERVICE_TEMPORARILY_UNAVAILABLE", "message": "The service is temporarily unavailable.", "details": {}},
                "code": "SERVICE_TEMPORARILY_UNAVAILABLE",
                "message": "The service is temporarily unavailable.",
                "details": {},
                "instance": "",
                "request_id": "",
            },
        )


class PrivateArtifactTests(TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            OPERATIONS_PRIVATE_ARTIFACT_ROOT=self.temporary_directory.name
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.temporary_directory.cleanup)
        self.account = user("artifact@example.test", "+10000000043", "artifact-a")
        self.other = user("artifact-other@example.test", "+10000000044", "artifact-b")
        self.client = APIClient()

    def test_reconciled_report_is_csv_safe_and_owner_downloadable(self):
        TransactionHistoryEntry.objects.create(
            tenant_id="artifact-a",
            account=self.account,
            type="TRADE",
            asset="=HYPERLINK(\"unsafe\")",
            amount=Decimal("1.25"),
            fee=Decimal("0.01"),
            status="SETTLED",
            occurred_at=timezone.now(),
            source_ref="sim-safe",
        )
        job = ReportJob.objects.create(
            tenant_id="artifact-a",
            account=self.account,
            report_type="TRADE",
            parameters_hash="0" * 64,
            idempotency_key="report-private-1",
            reconciliation_passed=True,
        )
        self.assertEqual(generate_report_artifact(str(job.pk)), "COMPLETED")
        job.refresh_from_db()
        self.client.force_authenticate(self.account)
        response = self.client.get(f"/api/v1/reports/exports/{job.pk}/download")
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn("'=HYPERLINK", content)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="REPORT_DOWNLOADED", target=str(job.pk)
            ).exists()
        )

    def test_report_download_is_cross_tenant_safe_and_reconciliation_gated(self):
        job = ReportJob.objects.create(
            tenant_id="artifact-a",
            account=self.account,
            report_type="ACTIVITY",
            parameters_hash="0" * 64,
            idempotency_key="report-private-2",
            reconciliation_passed=False,
        )
        self.assertEqual(generate_report_artifact(str(job.pk)), "FAILED")
        self.client.force_authenticate(self.other)
        response = self.client.get(f"/api/v1/reports/exports/{job.pk}/download")
        self.assertEqual(response.status_code, 404)

    def test_artifact_failure_is_bounded_and_job_is_not_left_running(self):
        job = ReportJob.objects.create(
            tenant_id="artifact-a",
            account=self.account,
            report_type="ACTIVITY",
            parameters_hash="0" * 64,
            idempotency_key="report-storage-failure",
            reconciliation_passed=True,
        )
        with patch(
            "operations.tasks.write_private_artifact",
            side_effect=PermissionError("private storage unavailable"),
        ):
            with self.assertRaises(PermissionError):
                generate_report_artifact.run(str(job.pk))
        self.assertEqual(generate_report_artifact.max_retries, 3)
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")

    def test_privacy_export_excludes_internal_support_notes(self):
        case = SupportCase.objects.create(
            tenant_id="artifact-a",
            account=self.account,
            category="SECURITY",
            safe_summary="customer summary",
        )
        for visibility, body in (
            ("INTERNAL_NOTE", "employee-only investigation"),
            ("CUSTOMER_VISIBLE_MESSAGE", "customer-visible update"),
        ):
            SupportCaseEvent.objects.create(
                tenant_id="artifact-a",
                account=self.account,
                case=case,
                event_type="MESSAGE_ADDED",
                visibility=visibility,
                body_safe=body,
                actor=self.account,
            )
        job = PrivacyExportJob.objects.create(
            tenant_id="artifact-a",
            account=self.account,
            idempotency_key="privacy-private-1",
            policy_version="PRIVACY-EXPORT-SCHEMA-v1",
        )
        self.assertEqual(generate_privacy_export(str(job.pk)), "COMPLETED")
        self.client.force_authenticate(self.account)
        response = self.client.get(f"/api/v1/privacy/exports/{job.pk}/download")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(b"".join(response.streaming_content))
        exported_messages = [row["body_safe"] for row in payload["support_messages"]]
        self.assertEqual(exported_messages, ["customer-visible update"])
        self.assertNotIn("employee-only investigation", json.dumps(payload))


class PrivateNotificationRealtimeTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.a = user("socket-a@example.test", "+10000000041", brand="a")
        self.b = user("socket-b@example.test", "+10000000042", brand="b")

    def test_anonymous_connection_is_rejected(self):
        from FX.asgi import application

        async def scenario():
            communicator = WebsocketCommunicator(application, "/ws/v2/")
            connected, code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(code, 4401)

        async_to_sync(scenario)()

    def test_private_group_does_not_cross_accounts_or_tenants(self):
        from FX.asgi import application

        cache.set("ticket-a", self.a.pk, 120)
        cache.set("ticket-b", self.b.pk, 120)

        async def scenario():
            socket_a = WebsocketCommunicator(application, "/ws/v2/?ws_ticket=ticket-a")
            socket_b = WebsocketCommunicator(application, "/ws/v2/?ws_ticket=ticket-b")
            self.assertTrue((await socket_a.connect())[0])
            self.assertTrue((await socket_b.connect())[0])
            self.assertEqual((await socket_a.receive_json_from())["type"], "gateway.ready")
            self.assertEqual((await socket_b.receive_json_from())["type"], "gateway.ready")
            await get_channel_layer().group_send(
                notification_group("a", self.a.pk),
                {
                    "type": "notification.created",
                    "notification": {
                        "notification_id": "safe-id",
                        "category": "SECURITY",
                    },
                },
            )
            message = await socket_a.receive_json_from()
            self.assertEqual(message["notification"]["notification_id"], "safe-id")
            self.assertTrue(await socket_b.receive_nothing(timeout=0.05))
            await socket_a.disconnect()
            await socket_b.disconnect()

        async_to_sync(scenario)()

    def test_realtime_payload_excludes_delivery_diagnostics(self):
        notification = Notification.objects.create(
            tenant_id="a",
            account=self.a,
            type="NEW_DEVICE",
            category="SECURITY",
            channel="IN_APP",
            template_version="1",
            dedup_key="safe",
            failure_reason_safe="internal diagnostic",
        )
        payload = realtime_notification_payload(notification)
        self.assertNotIn("failure_reason_safe", payload)
        self.assertNotIn("account", payload)
        self.assertNotIn("tenant_id", payload)
