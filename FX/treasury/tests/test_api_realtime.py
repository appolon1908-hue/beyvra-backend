import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import resolve, Resolver404
from rest_framework.test import APIClient

from integrations.models import Organization, OrganizationMembership
from treasury.models import TreasuryAccount, TreasuryException, TreasuryReconciliationRun, TreasuryTransferPlan
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

    def test_plan_action_and_reconciliation_replay_exactly_once(self):
        plan = TreasuryTransferPlan.objects.create(
            tenant=self.tenant, institution_id=uuid.uuid4(), plan_type="CASH", state="VALIDATED",
            currency_or_asset="USD", required_amount_or_quantity="10", policy_version="simulation-v1",
            idempotency_key="plan-fixture",
        )
        headers = {
            "HTTP_IDEMPOTENCY_KEY": "plan-action-test", "HTTP_X_REQUEST_ID": "75c9b384-dcaa-46e4-872a-bf6812f14001",
            "HTTP_IF_MATCH": "VALIDATED",
        }
        first = self.api.post(f"/api/v1/operator/treasury/transfer-plans/{plan.pk}/simulate", {}, format="json", **headers)
        replay = self.api.post(f"/api/v1/operator/treasury/transfer-plans/{plan.pk}/simulate", {}, format="json", **headers)
        self.assertEqual(first.status_code, 200); self.assertEqual(replay.data, first.data)
        plan.refresh_from_db(); self.assertEqual(plan.state, "SIMULATED")

        reconcile_headers = {"HTTP_IDEMPOTENCY_KEY": "reconcile-test", "HTTP_X_REQUEST_ID": "75c9b384-dcaa-46e4-872a-bf6812f14002"}
        first = self.api.post("/api/v1/operator/treasury/reconciliation/run", {}, format="json", **reconcile_headers)
        replay = self.api.post("/api/v1/operator/treasury/reconciliation/run", {}, format="json", **reconcile_headers)
        self.assertEqual(first.status_code, 200); self.assertEqual(replay.data, first.data)
        self.assertEqual(TreasuryReconciliationRun.objects.count(), 1)

    def test_exception_resolution_uses_persisted_independent_maker(self):
        membership = OrganizationMembership.objects.get(user=self.user, organization=self.tenant)
        membership.role = "treasury_manager"; membership.save(update_fields=("role",))
        item = TreasuryException.objects.create(
            tenant=self.tenant, institution_id=uuid.uuid4(), exception_type="SIMULATION_MISMATCH",
            severity="HIGH", state="OPEN", source_ref="fixture", evidence_hash="0" * 64,
        )
        assign_headers = {
            "HTTP_IDEMPOTENCY_KEY": "assign-test", "HTTP_X_REQUEST_ID": "75c9b384-dcaa-46e4-872a-bf6812f14003",
            "HTTP_IF_MATCH": "OPEN:HIGH:-",
        }
        assigned = self.api.post(f"/api/v1/operator/treasury/exceptions/{item.pk}/assign", {}, format="json", **assign_headers)
        self.assertEqual(assigned.status_code, 200)
        assigned_version = assigned.data["data"]["version"]
        self_attempt = self.api.post(
            f"/api/v1/operator/treasury/exceptions/{item.pk}/resolve", {"maker_ref": "someone-else"}, format="json",
            HTTP_IDEMPOTENCY_KEY="resolve-self-test", HTTP_X_REQUEST_ID="75c9b384-dcaa-46e4-872a-bf6812f14004", HTTP_IF_MATCH=assigned_version,
        )
        self.assertEqual(self_attempt.status_code, 409)

        checker = get_user_model().objects.create_user(email="treasury-checker@example.test", password="test-only")
        OrganizationMembership.objects.create(user=checker, organization=self.tenant, role="treasury_manager")
        self.api.force_authenticate(checker)
        resolve_headers = {
            "HTTP_IDEMPOTENCY_KEY": "resolve-test", "HTTP_X_REQUEST_ID": "75c9b384-dcaa-46e4-872a-bf6812f14005",
            "HTTP_IF_MATCH": assigned_version,
        }
        resolved = self.api.post(f"/api/v1/operator/treasury/exceptions/{item.pk}/resolve", {"resolution_code": "REVIEWED"}, format="json", **resolve_headers)
        replay = self.api.post(f"/api/v1/operator/treasury/exceptions/{item.pk}/resolve", {"resolution_code": "REVIEWED"}, format="json", **resolve_headers)
        self.assertEqual(resolved.status_code, 200); self.assertEqual(replay.data, resolved.data)
        item.refresh_from_db(); self.assertEqual(item.state, "RESOLVED")
