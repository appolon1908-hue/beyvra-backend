from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.trading.models import SimulatedAccount
from integrations.models import Organization, OrganizationMembership


class CanonicalDemoAuthorityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="canonical-demo@example.invalid", password="test-pass", phone_number="+12025550182"
        )
        self.organization = Organization.objects.create(name="Canonical demo tenant")
        OrganizationMembership.objects.create(user=self.user, organization=self.organization)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.headers = {"HTTP_X_ORGANIZATION_ID": str(self.organization.id)}

    def test_legacy_demo_mutation_and_trade_routes_are_retired(self):
        self.assertEqual(self.client.post("/api/v1/demo/orders", {}, **self.headers).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/demo/trades", **self.headers).status_code, 404)
        self.assertEqual(self.client.post("/api/v1/demo/wallet/refill", {}, **self.headers).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/demo/wallet", **self.headers).status_code, 404)

    def test_workspace_uses_canonical_simulated_account(self):
        response = self.client.get("/api/v1/workspace/bootstrap", **self.headers)
        self.assertEqual(response.status_code, 200)
        account = SimulatedAccount.objects.get(subject_ref=str(self.user.pk))
        self.assertEqual(response.data["account"]["id"], str(account.id))
        self.assertEqual(response.data["realtime"]["demo_order_channel"], f"simulation.order.sim-{self.user.pk}")
