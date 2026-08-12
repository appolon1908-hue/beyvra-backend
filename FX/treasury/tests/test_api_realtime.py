import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import resolve, Resolver404
from rest_framework.test import APIClient

from integrations.models import Organization, OrganizationMembership
from treasury.models import TreasuryAccount
from ws.v2 import _channel_entry


class TreasuryApiRealtimeTests(TestCase):
    def setUp(self):
        self.tenant = Organization.objects.create(name="Tenant A")
        self.other = Organization.objects.create(name="Tenant B")
        self.user = get_user_model().objects.create_user(email="treasury@example.com", password="test-password-123")
        OrganizationMembership.objects.create(user=self.user, organization=self.tenant, role="treasury_analyst")
        self.account = TreasuryAccount.objects.create(tenant=self.tenant, institution_id=uuid.uuid4(), account_type="SIMULATION_CASH", currency="USD", environment="SIMULATION", status="ACTIVE", segregation_class="HOUSE", effective_from="2026-01-01T00:00:00Z")
        TreasuryAccount.objects.create(tenant=self.other, institution_id=uuid.uuid4(), account_type="SIMULATION_CASH", currency="EUR", environment="SIMULATION", status="ACTIVE", segregation_class="HOUSE", effective_from="2026-01-01T00:00:00Z")
        self.api = APIClient(); self.api.force_authenticate(self.user)

    def test_customer_api_is_tenant_scoped_and_provider_refs_hidden(self):
        response = self.api.get("/api/v1/treasury/accounts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertNotIn("external_account_ref", response.data["data"][0])
        self.assertTrue(response.data["simulation"])

    def test_operator_role_can_read_and_support_cannot(self):
        self.assertEqual(self.api.get("/api/v1/operator/treasury/accounts").status_code, 200)
        membership = OrganizationMembership.objects.get(user=self.user, organization=self.tenant)
        membership.role = "support"; membership.save(update_fields=("role",))
        self.assertEqual(self.api.get("/api/v1/operator/treasury/accounts").status_code, 403)

    def test_live_routes_do_not_resolve(self):
        for path in ("/api/v1/treasury/transfers/execute-live", f"/api/v1/operator/treasury/transfer-plans/{uuid.uuid4()}/execute-live"):
            with self.assertRaises(Resolver404): resolve(path)

    def test_treasury_realtime_channel_is_private_and_resumable(self):
        pattern, entry = _channel_entry(f"treasury.{self.tenant.id}")
        self.assertEqual(pattern, "treasury.{tenant_id}")
        self.assertEqual(entry["visibility"], "private")
        self.assertTrue(entry["resume_supported"])
        self.assertEqual(entry["snapshot_provider"], "/api/v1/treasury/liquidity")

    def test_other_tenant_id_cannot_select_data(self):
        response = self.api.get("/api/v1/treasury/accounts", HTTP_X_TENANT_ID=str(self.other.id))
        self.assertEqual(response.status_code, 403)
