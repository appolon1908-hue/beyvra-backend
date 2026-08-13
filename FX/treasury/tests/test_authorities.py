import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from integrations.models import Organization
from treasury.models import (
    CollateralMobilityPolicy, FundingRequirement, LiquidityBufferPolicy,
    LiquidityStressScenario, TreasuryAccount, TreasuryCashPosition,
    TreasuryCollateralPosition, TreasuryTransferPlan,
)
from treasury.services import (
    CashPositionService, CollateralMobilityService, IntradayFundingService, LiquidityForecastService,
    LiquidityService, LiquidityStressService, SettlementFundingService,
    TreasuryPlanner, TreasuryReconciler,
)


class TreasuryAuthorityTests(TestCase):
    def setUp(self):
        self.tenant = Organization.objects.create(name="Synthetic Institution")
        self.other = Organization.objects.create(name="Other Synthetic Institution")
        now = timezone.now()
        common = dict(tenant=self.tenant, institution_id=uuid.uuid4(), environment="SIMULATION", status="ACTIVE", effective_from=now)
        self.house = TreasuryAccount.objects.create(account_type="HOUSE_REFERENCE", segregation_class="HOUSE", currency="USD", **common)
        self.settlement = TreasuryAccount.objects.create(account_type="SETTLEMENT_REFERENCE", segregation_class="CLEARING", currency="USD", **common)
        self.client_account = TreasuryAccount.objects.create(account_type="SEGREGATED_REFERENCE", segregation_class="CLIENT_SEGREGATED", currency="USD", **common)
        TreasuryCashPosition.objects.create(treasury_account=self.house, currency="USD", gross_amount="1000", reserved_amount="100", available_amount="900", encumbered_amount="100", unencumbered_amount="900", source="SIMULATION_LEDGER", as_of=now)
        TreasuryCashPosition.objects.create(treasury_account=self.client_account, currency="USD", gross_amount="5000", reserved_amount="0", available_amount="5000", encumbered_amount="0", unencumbered_amount="5000", source="SIMULATION_LEDGER", as_of=now)

    def test_simulation_is_mandatory(self):
        account = TreasuryAccount(tenant=self.tenant, account_type="HOUSE_REFERENCE", environment="SIMULATION", segregation_class="HOUSE", effective_from=timezone.now(), simulation=False)
        with self.assertRaises(ValidationError): account.full_clean()

    def test_cash_is_projection_and_nonnegative(self):
        self.assertEqual(CashPositionService.available(self.tenant, "USD"), Decimal("5900"))
        row = TreasuryCashPosition(treasury_account=self.house, currency="USD", gross_amount=-1, available_amount=-1, unencumbered_amount=0, source="SIMULATION_LEDGER", as_of=timezone.now())
        with self.assertRaises(ValidationError): row.full_clean()

    def test_liquidity_respects_buffer(self):
        LiquidityBufferPolicy.objects.create(tenant=self.tenant, scope_type="INSTITUTION", currency="USD", buffer_type="FIXED_AMOUNT", buffer_value="250", status="SIMULATION", policy_version="v1", effective_from=timezone.now())
        snapshot = LiquidityService.calculate(self.tenant, self.house.institution_id, "USD")
        self.assertEqual(snapshot.liquidity_buffer, Decimal("250"))
        self.assertEqual(snapshot.liquidity_surplus_deficit, Decimal("5650"))

    def test_client_segregated_assets_cannot_fund_house(self):
        TreasuryCollateralPosition.objects.create(treasury_account=self.client_account, instrument_id_or_asset="UST", quantity=100, reference_price=1, gross_value=100, haircut_rate=0, eligible_value=100, encumbered_quantity=0, free_quantity=100, currency="USD", quality_state="ELIGIBLE", as_of=timezone.now())
        CollateralMobilityPolicy.objects.create(tenant=self.tenant, from_account_type=self.client_account.account_type, to_account_type=self.house.account_type, asset_class="FIXED_INCOME", asset="UST", movement_type="INTERNAL_TRANSFER", allowed=True, settlement_delay=timedelta(), policy_version="v1", effective_from=timezone.now())
        result = CollateralMobilityService.preview(self.tenant, self.client_account.id, self.house.id, "UST", "10")
        self.assertFalse(result["allowed"])
        self.assertIn("SEGREGATION_CONFLICT", result["reason_codes"])

    def test_stale_collateral_is_denied(self):
        TreasuryCollateralPosition.objects.create(treasury_account=self.house, instrument_id_or_asset="UST", quantity=100, reference_price=1, gross_value=100, haircut_rate=0, eligible_value=100, encumbered_quantity=0, free_quantity=100, currency="USD", quality_state="STALE", as_of=timezone.now()-timedelta(days=1))
        result = CollateralMobilityService.preview(self.tenant, self.house.id, self.settlement.id, "UST", "10")
        self.assertFalse(result["allowed"])
        self.assertIn("STALE_COLLATERAL", result["reason_codes"])

    def test_plan_is_idempotent_and_excludes_client_assets(self):
        plan1 = TreasuryPlanner.generate_cash_plan(self.tenant, self.house.institution_id, "USD", 500, self.settlement, "same-key")
        plan2 = TreasuryPlanner.generate_cash_plan(self.tenant, self.house.institution_id, "USD", 500, self.settlement, "same-key")
        self.assertEqual(plan1.id, plan2.id)
        self.assertEqual(TreasuryTransferPlan.objects.count(), 1)
        self.assertTrue(all(i.source_account_id != self.client_account.id for i in plan1.items.all()))

    def test_plan_idempotency_key_rejects_changed_payload(self):
        TreasuryPlanner.generate_cash_plan(self.tenant, self.house.institution_id, "USD", 500, self.settlement, "conflict-key")
        with self.assertRaisesMessage(ValueError, "IDEMPOTENCY_CONFLICT"):
            TreasuryPlanner.generate_cash_plan(self.tenant, self.house.institution_id, "USD", 501, self.settlement, "conflict-key")

    def test_tenant_isolation(self):
        self.assertEqual(CashPositionService.get_positions(self.other).count(), 0)
        self.assertEqual(TreasuryTransferPlan.objects.filter(tenant=self.other).count(), 0)

    def test_settlement_shortfall_is_explicit(self):
        req = FundingRequirement.objects.create(tenant=self.tenant, institution_id=self.house.institution_id, requirement_type="SETTLEMENT", currency_or_asset="USD", amount_or_quantity=9999, due_at=timezone.now(), priority="CRITICAL_SETTLEMENT", source_ref="settlement-1", state="CONFIRMED_SIMULATION", policy_version="v1")
        self.assertEqual(SettlementFundingService.evaluate(req)["status"], "FUNDING_SHORTFALL")

    def test_forecast_does_not_invent_inflows(self):
        forecast = LiquidityForecastService.calculate(self.tenant, self.house.institution_id, "USD")
        self.assertEqual(forecast.expected_inflows, 0)

    def test_intraday_uses_peak_not_end_of_day_net(self):
        start = timezone.now()
        window = IntradayFundingService.calculate(self.tenant, self.house.institution_id, "USD", start, start + timedelta(hours=8), 100, [
            {"at": start + timedelta(hours=1), "direction": "OUTFLOW", "amount": 250},
            {"at": start + timedelta(hours=2), "direction": "INFLOW", "amount": 300},
        ])
        self.assertEqual(window.peak_funding_need, 150)
        self.assertEqual(window.closing_liquidity, 150)

    def test_stress_and_reconciliation_are_read_only(self):
        scenario = LiquidityStressScenario.objects.create(code="CASH_25", name="Cash decline", scenario_type="MARKET_DROP", parameters_json_safe={"cash_factor": "0.75", "outflow_factor": "2"}, policy_version="v1")
        result = LiquidityStressService.run(self.tenant, self.house.institution_id, "USD", scenario)
        self.assertTrue(result.simulation)
        run = TreasuryReconciler.run(self.tenant, "a" * 40)
        self.assertEqual(run.status, "PASS")

    def test_no_live_execution_route_exists(self):
        self.assertEqual(self.client.get("/api/v1/treasury/transfers/execute-live").status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/operator/treasury/transfer-plans/{uuid.uuid4()}/execute-live").status_code, 404)
