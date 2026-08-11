import uuid
from datetime import timedelta
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, TransactionTestCase
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
    SecurityEvent,
    Statement,
    SupportCase,
    SupportCaseEvent,
    TransactionHistoryEntry,
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
    notification_group,
    realtime_notification_payload,
    record_delivery_failure,
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
            {"code": "RESOURCE_NOT_FOUND", "message": "Resource not found."},
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
                approver=self.maker,
                approver_roles={"security_manager"},
            )

    def test_independent_manager_can_approve_once(self):
        action = self.action()
        approved = approve_operator_request(
            request_id=action.pk,
            approver=self.checker,
            approver_roles={"security_manager"},
        )
        self.assertEqual(approved.status, "APPROVED")
        with self.assertRaises(PermissionError):
            approve_operator_request(
                request_id=action.pk,
                approver=self.checker,
                approver_roles={"security_manager"},
            )

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
            approver=self.checker,
            approver_roles={"security_manager"},
        )
        executed = execute_operator_request(
            request_id=action.pk,
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
            approver=self.checker,
            approver_roles={"security_manager"},
        )
        with self.assertRaisesRegex(PermissionError, "EXTERNAL_AUTHORITY_REQUIRED"):
            execute_operator_request(
                request_id=action.pk,
                executor=self.checker,
                executor_roles={"security_manager"},
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

    def test_wrong_tenant_account_cannot_be_frozen(self):
        outsider = user("outsider@example.test", "+10000000035", brand="tenant-b")
        client = APIClient()
        client.force_authenticate(self.checker)
        response = client.post(
            f"/api/internal/v1/accounts/{outsider.pk}/freeze",
            {"level": "FULL"},
            format="json",
            HTTP_X_BEYVRA_TENANT="tenant-a",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(AccountFreeze.objects.filter(account=outsider).exists())

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
                "code": "FEATURE_DISABLED",
                "message": "This feature is currently unavailable.",
            },
        )


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
