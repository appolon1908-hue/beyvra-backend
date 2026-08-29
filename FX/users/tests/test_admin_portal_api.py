from uuid import uuid4

from django.test import override_settings
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from financial_boundary.models import ProviderWebhookInbox
from operations.models import AuditEvent, SecurityEvent
from users.models import User


@override_settings(DEPLOYMENT_ENV="test", REALTIME_V2_ENABLED=True)
class AdminPortalApiTests(APITestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            email="admin-portal-client@example.test",
            password="safe-test-password",
            phone_number="+12025550310",
        )
        self.contractor = User.objects.create_user(
            email="admin-portal-contractor@example.test",
            password="safe-test-password",
            phone_number="+12025550311",
            role="Contractor",
        )
        self.admin = User.objects.create_user(
            email="admin-portal-admin@example.test",
            password="safe-test-password",
            phone_number="+12025550312",
            role="Admin",
            is_staff=True,
        )

    def test_admin_portal_routes_resolve_at_canonical_v1_boundary(self):
        routes = {
            "/api/v1/admin/portal/summary": "admin_portal_summary",
            "/api/v1/admin/portal/users": "admin_portal_users",
            "/api/v1/admin/portal/events": "admin_portal_events",
        }
        for path, expected_name in routes.items():
            with self.subTest(path=path):
                self.assertEqual(resolve(path).view_name, expected_name)

    def test_admin_summary_fails_closed_for_non_admin_sessions(self):
        self.assertIn(APIClient().get("/api/v1/admin/portal/summary").status_code, {401, 403})

        client = APIClient()
        client.force_authenticate(self.client_user)
        self.assertEqual(client.get("/api/v1/admin/portal/summary").status_code, 403)

        client.force_authenticate(self.contractor)
        self.assertEqual(client.get("/api/v1/admin/portal/summary").status_code, 403)

    def test_admin_summary_returns_control_room_counts(self):
        AuditEvent.objects.create(
            tenant_id="default",
            actor=self.admin,
            role="Admin",
            action="USER_REVIEWED",
            target="user:admin-portal-client",
        )
        SecurityEvent.objects.create(
            tenant_id="default",
            account=self.client_user,
            event_type="SUSPICIOUS_ACTIVITY",
            occurred_at=timezone.now(),
            source="test",
            risk_level="HIGH",
        )
        ProviderWebhookInbox.objects.create(
            provider="alpaca",
            external_event_id="evt-admin-portal-1",
            tenant_id=uuid4(),
            payload_hash="a" * 64,
            signature_timestamp=timezone.now(),
            status=ProviderWebhookInbox.Status.DEAD_LETTER,
            failure_code="TEST_FAILURE",
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/v1/admin/portal/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["users"]["total"], 3)
        self.assertEqual(payload["users"]["contractors"], 1)
        self.assertGreaterEqual(payload["users"]["admins"], 1)
        self.assertEqual(payload["webhooks"]["deadLetter"], 1)
        self.assertEqual(payload["security"]["openHighRiskEvents"], 1)
        self.assertEqual(payload["system"]["environment"], "test")
        self.assertEqual(payload["audit"]["recent"][0]["action"], "USER_REVIEWED")

    def test_admin_users_endpoint_exposes_only_admin_safe_profile_fields(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/v1/admin/portal/users?limit=2")

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 2)
        for row in results:
            self.assertIn("email", row)
            self.assertIn("role", row)
            self.assertNotIn("phone_number", row)
            self.assertNotIn("address", row)
            self.assertNotIn("password", row)

    def test_admin_events_endpoint_returns_audit_and_webhook_summaries_without_payloads(self):
        ProviderWebhookInbox.objects.create(
            provider="alpaca",
            external_event_id="evt-admin-portal-2",
            tenant_id=uuid4(),
            payload_hash="b" * 64,
            signature_timestamp=timezone.now(),
            status=ProviderWebhookInbox.Status.PENDING,
        )
        AuditEvent.objects.create(
            tenant_id="default",
            actor=self.admin,
            role="Admin",
            action="WEBHOOK_REVIEWED",
            target="webhook:alpaca",
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/v1/admin/portal/events")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["audit"][0]["action"], "WEBHOOK_REVIEWED")
        self.assertEqual(payload["webhooks"][0]["provider"], "alpaca")
        self.assertNotIn("encrypted_payload", payload["webhooks"][0])
        self.assertNotIn("payloadHash", payload["webhooks"][0])
