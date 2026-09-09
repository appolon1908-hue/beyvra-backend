import hashlib
import json
import time
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.compliance.models import ComplianceProfile
from pricing_authority.models import AccountPlan, AccountPlanAssignment, AccountPlanVersion, Entitlement, PlanEntitlement
from users.models import User


from apps.foundation.models import IdempotencyRecord
from .models import DemoAccount, DemoLedgerEntry, Organization, OrganizationMembership, ServiceToken


@override_settings(API_TOKEN_PEPPER="integration-test-pepper")
class IntegrationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Synthetic CRM")
        self.token, self.raw = ServiceToken.issue(self.org, "test", ["users:write"])
        self.payload = {"external_user_id": "crm-user-1", "first_name": "Demo", "last_name": "Customer", "email": "demo1@example.invalid", "phone": "+15555550100", "organization_id": str(self.org.id), "consent": {"terms_accepted": True}}

    def test_create_and_idempotent_demo_ledger(self):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {self.raw}", "HTTP_IDEMPOTENCY_KEY": "synthetic-1", "HTTP_X_REQUEST_ID": "84acb666-d825-4dba-b579-c7feb4af2001"}
        response = self.client.post("/api/v1/users", self.payload, format="json", **headers)
        self.assertEqual(response.status_code, 201)
        replay = self.client.post("/api/v1/users", self.payload, format="json", **headers)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(DemoAccount.objects.count(), 1)
        self.assertEqual(DemoLedgerEntry.objects.get().amount_cents, 200000)
        self.assertFalse(DemoAccount.objects.get().withdrawable)
        conflict = self.client.post("/api/v1/users", {**self.payload, "email": "changed@example.invalid"}, format="json", **headers)
        self.assertEqual(conflict.status_code, 409)

    def test_caller_cannot_set_balance_or_role(self):
        payload = {**self.payload, "balance": "999999", "role": "Admin"}
        response = self.client.post("/api/v1/users", payload, format="json", HTTP_AUTHORIZATION=f"Bearer {self.raw}", HTTP_IDEMPOTENCY_KEY="synthetic-2", HTTP_X_REQUEST_ID="84acb666-d825-4dba-b579-c7feb4af2002")
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email=self.payload["email"])
        self.assertEqual(user.role, "User")


class ControlPlaneContextTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = User.objects.create_user(
            email="control-plane@example.test",
            password="safe-test-password",
            phone_number="+15555550111",
        )
        self.org = Organization.objects.create(name="Control Plane Tenant")
        OrganizationMembership.objects.create(user=self.user, organization=self.org, role="owner")
        self.profile = ComplianceProfile.objects.create(user=self.user, organization=self.org)
        plan = AccountPlan.objects.create(
            code="CONTROL_PLANE_FIXTURE",
            name="Control plane fixture",
            status="ACTIVE",
            effective_from=self.now,
        )
        version = AccountPlanVersion.objects.create(
            plan=plan,
            version=1,
            status="ACTIVE",
            effective_from=self.now,
        )
        AccountPlanAssignment.objects.create(
            account=self.user,
            tenant_ref=str(self.org.id),
            plan_version=version,
            source="TEST",
            effective_from=self.now,
        )
        entitlement = Entitlement.objects.create(
            code="MARKET_DATA_DELAYED",
            category="MARKET_DATA",
            effective_from=self.now,
        )
        PlanEntitlement.objects.create(
            plan_version=version,
            entitlement=entitlement,
            enabled=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_control_plane_composes_canonical_authorities_without_duplicate_entitlements(self):
        response = self.client.get("/api/v1/control-plane/context")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tenant"]["tenant_id"], str(self.org.id))
        self.assertEqual(response.data["plan"]["code"], "CONTROL_PLANE_FIXTURE")
        codes = [item["code"] for item in response.data["entitlements"]]
        self.assertEqual(codes, ["MARKET_DATA_DELAYED"])
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(response.data["market_data"]["access"], "DELAYED")
        self.assertEqual(response.data["authorities"]["tenant"], "integrations.OrganizationMembership")
        self.assertEqual(ComplianceProfile.objects.get(pk=self.profile.pk).eligibility_decisions.count(), 0)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_multi_tenant_account_requires_explicit_header(self):
        other = Organization.objects.create(name="Second Tenant")
        OrganizationMembership.objects.create(user=self.user, organization=other)

        ambiguous = self.client.get("/api/v1/control-plane/context")
        selected = self.client.get(
            "/api/v1/control-plane/context",
            HTTP_X_ORGANIZATION_ID=str(self.org.id),
        )

        self.assertEqual(ambiguous.status_code, 400)
        self.assertEqual(ambiguous.data["code"], "TENANT_SELECTION_REQUIRED")
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.data["tenant"]["selection_source"], "request-header")

    def test_inactive_membership_is_never_selected(self):
        membership = OrganizationMembership.objects.get(user=self.user, organization=self.org)
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])

        response = self.client.get(
            "/api/v1/control-plane/context",
            HTTP_X_ORGANIZATION_ID=str(self.org.id),
        )

        self.assertEqual(response.status_code, 403)

    def test_legacy_tenant_context_delegates_and_is_deprecated(self):
        response = self.client.get("/api/v1/tenant/context")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tenantId"], str(self.org.id))
        self.assertEqual(response["Deprecation"], "true")


@override_settings(API_TOKEN_PEPPER="integration-test-pepper", DATA_ENCRYPTION_KEY="integration-test-data-key", WEBHOOK_MASTER_KEY="integration-webhook-test-key")
class IntegrationManagementCommandTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Integration management")
        self.admin = User.objects.create_user(email="integration-admin@example.test", password="test-only", is_staff=True)
        OrganizationMembership.objects.create(user=self.admin, organization=self.org, role="owner")
        self.client.force_authenticate(self.admin)

    def test_service_token_issue_replays_encrypted_secret(self):
        headers = {
            "HTTP_X_ORGANIZATION_ID": str(self.org.id), "HTTP_IDEMPOTENCY_KEY": "token-issue-test",
            "HTTP_X_REQUEST_ID": "84acb666-d825-4dba-b579-c7feb4af2003",
        }
        payload = {"name": "automation", "scopes": ["users:read"]}
        first = self.client.post("/api/v1/integrations/service-tokens", payload, format="json", **headers)
        replay = self.client.post("/api/v1/integrations/service-tokens", payload, format="json", **headers)
        conflict = self.client.post("/api/v1/integrations/service-tokens", {**payload, "scopes": ["users:write"]}, format="json", **headers)
        self.assertEqual(first.status_code, 201); self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.data, first.data); self.assertEqual(conflict.status_code, 409)
        self.assertEqual(ServiceToken.objects.filter(owner=self.admin).count(), 1)
        stored = IdempotencyRecord.objects.get(key="token-issue-test").response_body
        self.assertNotIn(first.data["token"], json.dumps(stored))

    def test_expired_service_token_idempotency_never_replays_secret(self):
        headers = {
            "HTTP_X_ORGANIZATION_ID": str(self.org.id), "HTTP_IDEMPOTENCY_KEY": "expired-token-issue",
            "HTTP_X_REQUEST_ID": "84acb666-d825-4dba-b579-c7feb4af2004",
        }
        payload = {"name": "automation", "scopes": ["users:read"]}
        first = self.client.post("/api/v1/integrations/service-tokens", payload, format="json", **headers)
        record = IdempotencyRecord.objects.get(key="expired-token-issue")
        record.expires_at = timezone.now() - timedelta(seconds=1); record.save(update_fields=["expires_at"])
        replay = self.client.post("/api/v1/integrations/service-tokens", payload, format="json", **headers)
        self.assertEqual(first.status_code, 201); self.assertEqual(replay.status_code, 410)
        self.assertNotIn("token", replay.data)

    def test_failed_import_response_is_durably_replayed(self):
        headers = {
            "HTTP_X_ORGANIZATION_ID": str(self.org.id), "HTTP_IDEMPOTENCY_KEY": "failed-import",
            "HTTP_X_REQUEST_ID": "84acb666-d825-4dba-b579-c7feb4af2005",
        }
        content = b"unsupported_column\nvalue\n"
        first = self.client.post("/api/v1/users/imports", {"file": SimpleUploadedFile("users.csv", content, content_type="text/csv")}, **headers)
        replay = self.client.post("/api/v1/users/imports", {"file": SimpleUploadedFile("users.csv", content, content_type="text/csv")}, **headers)
        self.assertEqual(first.status_code, 400); self.assertEqual(replay.status_code, 400)
        self.assertEqual(first.data, replay.data)

    def test_token_issue_rejects_malformed_input_without_creating_tokens(self):
        headers = {"HTTP_X_ORGANIZATION_ID": str(self.org.pk), "HTTP_IDEMPOTENCY_KEY": "invalid-token",
                   "HTTP_X_REQUEST_ID": "84acb666-d825-4dba-b579-c7feb4af2006"}
        for payload in ({"scopes": [{}]}, {"scopes": [["users:read"]]}, {"name": "x" * 121}, ["users:read"]):
            with self.subTest(payload=payload):
                response = self.client.post("/api/v1/integrations/service-tokens", payload, format="json", **headers)
                self.assertEqual(response.status_code, 400)
        self.assertFalse(ServiceToken.objects.exists())
        self.assertFalse(IdempotencyRecord.objects.exists())

    def test_missing_token_is_404_and_malformed_action_is_400(self):
        headers = {"HTTP_X_ORGANIZATION_ID": str(self.org.pk), "HTTP_IDEMPOTENCY_KEY": "token-action",
                   "HTTP_X_REQUEST_ID": "84acb666-d825-4dba-b579-c7feb4af2007", "HTTP_IF_MATCH": "ACTIVE"}
        missing = "/api/v1/integrations/service-tokens/00000000-0000-0000-0000-000000000001"
        self.assertEqual(self.client.post(missing, {"action": "revoke"}, format="json", **headers).status_code, 404)
        token, _ = ServiceToken.issue(self.org, "test", ["users:read"])
        response = self.client.post(f"/api/v1/integrations/service-tokens/{token.pk}", {"action": []}, format="json", **headers)
        self.assertEqual(response.status_code, 400)
        token.refresh_from_db()
        self.assertTrue(token.is_active)

    def test_crm_subscription_has_tenant_and_member_cannot_rotate_secret(self):
        from notifications.models import WebhookSubscription
        headers = {"HTTP_X_ORGANIZATION_ID": str(self.org.pk), "HTTP_IDEMPOTENCY_KEY": "crm-create",
                   "HTTP_X_REQUEST_ID": "84acb666-d825-4dba-b579-c7feb4af2008"}
        with patch("integrations.serializers.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]):
            response = self.client.post("/api/v1/integrations/crm/connections", {
                "name": "CRM", "endpoint": "https://crm.example.test", "secret": "long-enough-test-secret",
            }, format="json", **headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(WebhookSubscription.objects.get().organization_id, self.org.pk)
        member = User.objects.create_user(email="crm-member@example.test", password="test")
        OrganizationMembership.objects.create(user=member, organization=self.org, role="member")
        self.client.force_authenticate(member)
        denied = self.client.patch(f"/api/v1/integrations/crm/connections/{response.data['id']}", {
            "secret": "different-long-secret",
        }, format="json", **{**headers, "HTTP_IF_MATCH": response.data["updated_at"]})
        self.assertEqual(denied.status_code, 403)

    def test_revoked_token_cannot_be_rotated_into_new_access(self):
        token, _ = ServiceToken.issue(self.org, "revoked", ["users:read"])
        token.is_active = False
        token.revoked_at = timezone.now()
        token.save(update_fields=["is_active", "revoked_at"])
        headers = {"HTTP_X_ORGANIZATION_ID": str(self.org.pk), "HTTP_IDEMPOTENCY_KEY": "revoked-rotate",
                   "HTTP_X_REQUEST_ID": "84acb666-d825-4dba-b579-c7feb4af2009", "HTTP_IF_MATCH": "REVOKED"}
        response = self.client.post(f"/api/v1/integrations/service-tokens/{token.pk}", {"action": "rotate"}, format="json", **headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(ServiceToken.objects.count(), 1)
