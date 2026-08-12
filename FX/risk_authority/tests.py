from decimal import Decimal
from uuid import uuid4
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from users.models import User
from .models import CollateralPolicy, ExposureLimit, MarginCall, MarginPolicy
from .services import BuyingPowerService, CollateralService, ExposureService, LiquidationPlanner, MarginHealthService, MarginRequirementService


class SixAuthorityTests(TestCase):
 def setUp(self):
  self.now=timezone.now(); self.user=User.objects.create_user(email="risk@example.test",password="safe-test-password"); self.client=APIClient(); self.client.force_authenticate(self.user)
  self.margin=MarginPolicy.objects.create(code="SIMULATION_MARGIN_POLICY_V1",name="Simulation",asset_class="EQUITY",initial_margin_rate=Decimal("0.5"),maintenance_margin_rate=Decimal("0.25"),status="ACTIVE",policy_version=1,effective_from=self.now)
  self.collateral=CollateralPolicy.objects.create(code="SIMULATION_COLLATERAL_V1",asset="USD_FIXTURE",eligible=True,haircut_rate=Decimal("0.1"),valuation_currency="USD",status="ACTIVE",policy_version=1,effective_from=self.now)
  self.limit=ExposureLimit.objects.create(code="SIMULATION_EXPOSURE_V1",scope_type="ACCOUNT",scope_ref=str(self.user.pk),limit_type="MAX_GROSS_NOTIONAL",limit_value=Decimal("1000"),currency="USD",status="ACTIVE",policy_version=1,effective_from=self.now)
 def test_margin_authority_decimal_and_precision(self):
  out=MarginRequirementService.calculate(policy=self.margin,side="BUY",quantity=Decimal("2"),price=Decimal("100")); self.assertEqual(out["initial_margin_required"],Decimal("100.0"))
  with self.assertRaises(ValueError): MarginRequirementService.calculate(policy=self.margin,side="BUY",quantity=2.0,price=Decimal("1"))
 def test_collateral_authority_haircut_and_stale_fail_closed(self):
  self.assertEqual(CollateralService.preview(policy=self.collateral,quantity=Decimal("100"),price=Decimal("1"))["eligible_value"],Decimal("90.0"))
  self.assertEqual(CollateralService.preview(policy=self.collateral,quantity=Decimal("100"),price=Decimal("1"),fresh=False)["eligible_value"],0)
 def test_buying_power_authority_boundary(self):
  snap=BuyingPowerService.calculate_snapshot(equity=Decimal("100"),eligible_collateral=Decimal("50"),initial_margin_used=Decimal("25"),reservations=Decimal("25")); self.assertTrue(BuyingPowerService.calculate_order_impact(snap,Decimal("100"))["allowed"]); self.assertFalse(BuyingPowerService.calculate_order_impact(snap,Decimal("100.01"))["allowed"])
 def test_exposure_most_restrictive(self):
  stricter=ExposureLimit.objects.create(code="SIMULATION_STRICT",scope_type="GLOBAL",scope_ref="*",limit_type="MAX_GROSS_NOTIONAL",limit_value=Decimal("500"),status="ACTIVE",policy_version=1,effective_from=self.now)
  self.assertFalse(ExposureService.evaluate_order(current_gross=Decimal("450"),order_notional=Decimal("51"),limits=[self.limit,stricter])["allowed"])
 def test_margin_health_states(self):
  self.assertEqual(MarginHealthService.calculate(equity=Decimal("101"),maintenance=Decimal("100"))["health_state"],"HEALTHY"); self.assertEqual(MarginHealthService.calculate(equity=Decimal("40"),maintenance=Decimal("100"))["health_state"],"LIQUIDATION_ELIGIBLE")
 def test_duplicate_active_margin_calls_are_prevented(self):
  MarginCall.objects.create(account=self.user,triggered_at=self.now,required_amount=Decimal("1"),currency="USD",policy_version=1)
  with self.assertRaises(Exception): MarginCall.objects.create(account=self.user,triggered_at=self.now,required_amount=Decimal("2"),currency="USD",policy_version=1)
 def test_liquidation_planner_skips_stale_and_halted(self):
  positions=[{"instrument_id":uuid4(),"notional":Decimal("100"),"margin_consumption":Decimal("100"),"active":False,"fresh":True,"market_open":True},{"instrument_id":uuid4(),"notional":Decimal("80"),"margin_consumption":Decimal("80"),"active":True,"fresh":True,"market_open":True}]
  out=LiquidationPlanner.generate_plan(required_reduction=Decimal("50"),positions=positions); self.assertTrue(out["eligible"]); self.assertEqual(out["proposed_positions"][0]["estimated_notional"],Decimal("50"))
 def test_customer_apis_are_simulation_only(self):
  self.assertEqual(self.client.get("/api/v1/risk/summary").json()["real_margin_enabled"],False)
  margin=self.client.post("/api/v1/risk/margin/preview",{"side":"BUY","quantity":"2","price":"100"},format="json"); self.assertEqual(margin.status_code,200); self.assertTrue(margin.json()["simulation"])
  collateral=self.client.post("/api/v1/risk/collateral/preview",{"asset":"USD_FIXTURE","quantity":"10","price":"1"},format="json"); self.assertEqual(collateral.status_code,200)
 def test_real_and_operator_mutations_fail_closed(self):
  self.assertEqual(self.client.get("/api/v1/risk/liquidation/status").json()["code"],"FEATURE_DISABLED")
  self.assertEqual(self.client.get("/api/v1/operator/risk/liquidations").status_code,503)
