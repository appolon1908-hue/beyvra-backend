import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from users.models import User

from .models import (
    AccountDeletionRequest,
    AccountFreeze,
    AccountSession,
    AuditEvent,
    LegalHold,
    Notification,
    OperatorActionRequest,
    OperatorRole,
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

    def test_audit_is_immutable(self):
        audit = AuditEvent.objects.create(
            tenant_id="tenant-a", actor=self.checker, action="TEST", target="safe"
        )
        audit.reason = "mutated"
        with self.assertRaises(ValidationError):
            audit.save()
        with self.assertRaises(ValidationError):
            audit.delete()

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


class ExportSafetyTests(TestCase):
    def test_csv_formula_prefixes_are_neutralized(self):
        for prefix in "=+-@":
            self.assertEqual(csv_safe(prefix + "cmd"), "'" + prefix + "cmd")
        self.assertEqual(csv_safe("normal"), "normal")
