from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from integrations.models import Organization, OrganizationMembership
from wallet.constants import DEMO_WALLET_NAME
from wallet.models import Currency, Wallet


class DemoTenantIsolationTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            email="tenant-owner@example.invalid",
            password="test-pass",
            phone_number="+12025550190",
            is_guest_demo=True,
        )
        self.user = user
        self.tenant_a = Organization.objects.create(name="Tenant A")
        self.tenant_b = Organization.objects.create(name="Tenant B")
        OrganizationMembership.objects.create(user=user, organization=self.tenant_a, role="member")
        OrganizationMembership.objects.create(user=user, organization=self.tenant_b, role="member")
        currency = Currency.objects.create(name="Tenant Demo", symbol="TD", longer_name="Tenant Demo Dollar")
        self.wallet = Wallet.objects.create(
            user=user,
            organization=self.tenant_a,
            name=DEMO_WALLET_NAME,
            currency=currency,
            balance=Decimal("10000.00"),
            is_real=False,
        )
        self.client = APIClient()
        self.client.force_authenticate(user)

    def test_wallet_is_denied_under_another_tenant_context(self):
        response = self.client.get(
            "/api/v1/demo/wallet",
            HTTP_X_ORGANIZATION_ID=str(self.tenant_b.id),
        )
        self.assertEqual(response.status_code, 404)

    def test_trade_history_does_not_cross_tenant_context(self):
        response = self.client.get(
            "/api/v1/demo/trades",
            HTTP_X_ORGANIZATION_ID=str(self.tenant_b.id),
        )
        self.assertEqual(response.status_code, 404)

    def test_workspace_bootstrap_is_tenant_scoped_and_demo_only(self):
        response = self.client.get("/api/v1/workspace/bootstrap", HTTP_X_ORGANIZATION_ID=str(self.tenant_a.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["account"]["kind"], "DEMO")
        self.assertTrue(response.data["account"]["demoOnly"])
        self.assertEqual(response.data["realtime"], {
            "demo_order_channel": f"simulation.order.sim-{self.user.id}",
            "demo_execution_channel": f"simulation.execution.sim-{self.user.id}",
        })
        self.assertFalse(response.data["features"]["realTrading"])
        other = self.client.get("/api/v1/workspace/bootstrap", HTTP_X_ORGANIZATION_ID=str(self.tenant_b.id))
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.data["tenant"]["id"], str(self.tenant_b.id))
        self.assertNotEqual(other.data["account"]["id"], response.data["account"]["id"])
