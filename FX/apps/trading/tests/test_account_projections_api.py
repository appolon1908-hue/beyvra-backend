import uuid
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from apps.trading.models import SimulatedAccount
from users.models import User
from apps.compliance.domain import AccountState, AmlState, JurisdictionState, KycState, SanctionsState
from apps.compliance.models import ComplianceProfile
from integrations.models import Organization, OrganizationMembership


SIMULATION = override_settings(
    DEPLOYMENT_ENV="test",
    SIMULATED_TRADING_ENABLED=True,
    REAL_TRADING_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    REAL_MONEY_ENABLED=False,
)


@SIMULATION
class AccountProjectionsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email=f"acc-proj-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1202{uuid.uuid4().int % 10000000:07d}",
            password="testpassword"
        )
        org = Organization.objects.create(name=f"Org {uuid.uuid4()}")
        OrganizationMembership.objects.create(user=self.user, organization=org)
        ComplianceProfile.objects.create(
            user=self.user,
            organization=org,
            account_state=AccountState.ACTIVE,
            kyc_state=KycState.APPROVED,
            aml_state=AmlState.CLEARED,
            sanctions_state=SanctionsState.CLEAR,
            jurisdiction_state=JurisdictionState.SUPPORTED
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.headers = {"HTTP_X_BEYVRA_SIMULATION_MODE": "true"}

        self.account = SimulatedAccount.objects.create(
            tenant_ref="default",
            subject_ref=str(self.user.pk),
            account_ref=f"sim:{self.user.pk}",
            total_balance=10000,
            pending_balance=1500
        )

    def test_get_account_balances_projection(self):
        res = self.client.get(f"/api/v1/accounts/{self.account.id}/balances", **self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["currency"], "USD")
        self.assertEqual(data["cash"], "10000.000000000000000000")
        self.assertEqual(data["reserved_cash"], "1500.000000000000000000")
        self.assertEqual(data["available_cash"], "8500.000000000000000000")
        self.assertEqual(data["buying_power"], "8500.000000000000000000")
        self.assertEqual(data["quality"], "COMPLETE")

    def test_get_account_buying_power_projection(self):
        res = self.client.get(f"/api/v1/accounts/{self.account.id}/buying-power", **self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["buying_power"], "8500.000000000000000000")

    def test_get_account_cross_tenant_isolation(self):
        other_user = User.objects.create_user(
            email=f"other-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1202{uuid.uuid4().int % 10000000:07d}",
            password="testpassword"
        )
        client2 = APIClient()
        client2.force_authenticate(other_user)
        res = client2.get(f"/api/v1/accounts/{self.account.id}/balances", **self.headers)
        self.assertEqual(res.status_code, 404)
