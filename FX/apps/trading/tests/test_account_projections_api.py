import uuid
from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from apps.trading.models import SimulatedAccount, SimulatedReservation
from users.models import User
from apps.compliance.domain import AccountState, AmlState, JurisdictionState, KycState, SanctionsState
from apps.compliance.models import ComplianceProfile
from integrations.models import Organization, OrganizationMembership
from apps.post_trade.models import FeeSnapshot, Trade
from apps.valuation.models import TaxLot


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
        SimulatedReservation.objects.create(
            account=self.account,
            order_id=uuid.uuid4(),
            asset="USD",
            original_amount=1500,
            remaining_amount=1500,
            state=SimulatedReservation.State.ACTIVE,
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

    def test_get_account_transactions_projection_uses_trade_authority_fields(self):
        trade = Trade.objects.create(
            tenant_ref="default",
            account_ref=self.account.account_ref,
            order_id=uuid.uuid4(),
            execution_id=f"exec-{uuid.uuid4()}",
            instrument_id="BTC-USD",
            side="BUY",
            quantity="2",
            price="100",
            gross_notional="200",
            trade_currency="USD",
            execution_provider_id="sim-broker",
            venue_id="sim-venue",
            execution_mode="SIMULATION",
            trade_time=timezone.now(),
            captured_at=timezone.now(),
            settlement_date=timezone.now().date(),
            source_event_id=uuid.uuid4(),
            trade_state="SETTLED",
            simulation=True,
        )
        FeeSnapshot.objects.create(
            trade=trade,
            commission="1",
            exchange_fee="0",
            broker_fee="0",
            regulatory_fee="0",
            other_fee="0",
            total_fee="1",
            currency="USD",
            pricing_policy_version="test-v1",
        )

        response = self.client.get(f"/api/v1/accounts/{self.account.id}/transactions", **self.headers)
        self.assertEqual(response.status_code, 200)
        item = response.json()["results"][0]
        self.assertEqual(item["instrument_id"], "BTC-USD")
        self.assertEqual(item["fee"], "1.000000000000000000")
        self.assertEqual(item["status"], "SETTLED")

    def test_get_account_tax_lots_projection_uses_real_tax_lot_fields(self):
        TaxLot.objects.create(
            tenant_ref="default",
            account_ref=self.account.account_ref,
            instrument_id="BTC-USD",
            acquisition_date=timezone.now().date() - timedelta(days=2),
            original_quantity="5",
            remaining_quantity="3",
            unit_cost="100",
            total_cost="500",
            currency="USD",
            source_type="SIMULATION",
            status="PARTIALLY_DISPOSED",
            policy_version="test-v1",
        )

        response = self.client.get(f"/api/v1/accounts/{self.account.id}/tax-lots", **self.headers)
        self.assertEqual(response.status_code, 200)
        item = response.json()["results"][0]
        self.assertEqual(item["quantity"], "5.000000000000000000")
        self.assertEqual(item["disposed_quantity"], "2.000000000000000000")
        self.assertEqual(item["cost_basis_per_unit"], "100.000000000000000000")

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
