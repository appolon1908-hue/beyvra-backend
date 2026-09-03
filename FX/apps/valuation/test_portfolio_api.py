from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.trading.application.simulation import account_for
from apps.trading.models import SimulatedPosition
from integrations.models import Organization, OrganizationMembership
from users.models import User

from .models import PerformanceSnapshot, ValuationPrice


@override_settings(
    SIMULATED_TRADING_ENABLED=True,
    DEPLOYMENT_ENV="test",
    REAL_TRADING_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    REAL_MONEY_ENABLED=False,
)
class CanonicalPortfolioApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="portfolio-api@example.test", password="safe-password")
        organization = Organization.objects.create(name="Portfolio API Tenant")
        OrganizationMembership.objects.create(user=self.user, organization=organization)
        self.account = account_for(self.user)
        SimulatedPosition.objects.create(
            account=self.account,
            instrument_id="BTC-USD",
            quantity=Decimal("2"),
            average_price=Decimal("100"),
            realized_pnl=Decimal("5"),
        )
        self.now = timezone.now()
        ValuationPrice.objects.create(
            instrument_id="BTC-USD",
            valuation_time=self.now,
            price=Decimal("110"),
            currency="USD",
            price_type="MID",
            provider_id="certified-simulation-fixture",
            market_data_ref="fixture:btc-usd:110",
            quality_state="FRESH",
            market_status="OPEN",
            policy_id="SIMULATION",
            policy_version="1",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_summary_allocations_and_risk_share_one_valuation(self):
        summary = self.client.get("/api/v1/portfolio/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["market_value"], "220.00000000")
        self.assertEqual(summary.json()["unrealized_pnl"], "20.00000000")
        self.assertEqual(summary.json()["valuation_quality"], "COMPLETE")
        self.assertFalse(summary.json()["live_trading_enabled"])

        allocations = self.client.get("/api/v1/portfolio/allocations")
        self.assertEqual(allocations.json()["results"][0]["weight"], "1")

        risk = self.client.get("/api/v1/portfolio/risk")
        self.assertEqual(risk.json()["gross_exposure"], "220.00000000")
        self.assertEqual(risk.json()["largest_position_ratio"], "1")
        self.assertIsNone(risk.json()["value_at_risk"])
        self.assertEqual(risk.json()["advanced_risk_reason"], "CERTIFIED_HISTORY_AND_POLICY_REQUIRED")

    def test_performance_returns_only_persisted_evidence(self):
        empty = self.client.get("/api/v1/portfolio/performance?range=1M")
        self.assertEqual(empty.json()["quality"], "UNAVAILABLE")
        self.assertEqual(empty.json()["results"], [])

        PerformanceSnapshot.objects.create(
            tenant_ref="default",
            account_ref=f"sim:{self.user.pk}",
            period_start=self.now - timedelta(days=1),
            period_end=self.now,
            opening_value=Decimal("10000"),
            closing_value=Decimal("10100"),
            external_flows=Decimal("0"),
            income=Decimal("0"),
            fees=Decimal("0"),
            pnl=Decimal("100"),
            return_value=Decimal("0.01"),
            return_method="SIMPLE_RETURN",
            quality_state="FRESH",
            policy_version="1",
        )
        response = self.client.get("/api/v1/portfolio/performance?range=1M")
        self.assertEqual(response.json()["quality"], "COMPLETE")
        self.assertEqual(response.json()["results"][0]["return"], "0.010000000000000000")
