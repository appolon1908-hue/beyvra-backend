import hashlib
import json
import time
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.compliance.models import ComplianceProfile
from pricing_authority.models import AccountPlan, AccountPlanAssignment, AccountPlanVersion, Entitlement, PlanEntitlement
from users.models import User
from .models import DemoAccount, DemoLedgerEntry, IntegrationAuditEvent, Organization, OrganizationMembership, ServiceToken


@override_settings(API_TOKEN_PEPPER="integration-test-pepper")
class IntegrationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Synthetic CRM")
        self.token, self.raw = ServiceToken.issue(self.org, "test", ["users:write"])
        self.payload = {"external_user_id": "crm-user-1", "first_name": "Demo", "last_name": "Customer", "email": "demo1@example.invalid", "phone": "+15555550100", "organization_id": str(self.org.id), "consent": {"terms_accepted": True}}

    def test_create_and_idempotent_demo_ledger(self):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {self.raw}", "HTTP_IDEMPOTENCY_KEY": "synthetic-1"}
        response = self.client.post("/api/v1/users", self.payload, format="json", **headers)
        self.assertEqual(response.status_code, 201)
        replay = self.client.post("/api/v1/users", self.payload, format="json", **headers)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(DemoAccount.objects.count(), 1)
        self.assertEqual(DemoLedgerEntry.objects.get().amount_cents, 200000)
        self.assertFalse(DemoAccount.objects.get().withdrawable)

    def test_caller_cannot_set_balance_or_role(self):
        payload = {**self.payload, "balance": "999999", "role": "Admin"}
        response = self.client.post("/api/v1/users", payload, format="json", HTTP_AUTHORIZATION=f"Bearer {self.raw}", HTTP_IDEMPOTENCY_KEY="synthetic-2")
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email=self.payload["email"])
        self.assertEqual(user.role, "User")

    def test_public_intake_accepts_beyvra_lead_form_payload(self):
        payload = {
            "source": "demo-trading-platform",
            "name": "Demo Visitor",
            "email": "visitor@example.invalid",
            "interest": "Demo account",
            "goal": "I want to explore Beyvra charts and paper trading.",
            "consent": True,
        }

        response = self.client.post(
            "/api/v1/public/intake",
            payload,
            format="json",
            HTTP_X_REQUEST_ID="public-intake-test-1",
        )
        replay = self.client.post(
            "/api/v1/public/intake",
            payload,
            format="json",
            HTTP_X_REQUEST_ID="public-intake-test-1",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(response.data["status"], "submitted")
        self.assertEqual(replay.data["intake_id"], response.data["intake_id"])
        event = IntegrationAuditEvent.objects.get(action="public.intake")
        self.assertEqual(event.metadata["email"], payload["email"])
        self.assertEqual(event.metadata["source"], payload["source"])
        self.assertEqual(event.metadata["interest"], payload["interest"])


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
