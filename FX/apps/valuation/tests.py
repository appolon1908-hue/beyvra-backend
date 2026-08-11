from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from users.models import User
from .fx import FxValuationService
from .models import FxValuationRate, ValuationPrice
from .prices import ValuationPriceService
from .services import PerformanceReturnService, PortfolioNavService, PositionValuationService, UnrealizedPnLService


class ValuationAuthorityTests(TestCase):
 def setUp(self):
  self.now=timezone.now(); self.user=User.objects.create_user(email="valuation@example.test",password="safe-test-password"); self.client=APIClient(); self.client.force_authenticate(self.user)
  self.price=ValuationPrice.objects.create(instrument_id="fixture-instrument",valuation_time=self.now,price=Decimal("100"),currency="USD",price_type="MID",provider_id="fixture",market_data_ref="price-1",quality_state="FRESH",market_status="OPEN",policy_id="SIMULATION",policy_version="1")
 def test_price_authority_rejects_stale_and_selects_evidence(self):
  self.assertEqual(ValuationPriceService.resolve("fixture-instrument"),self.price)
  with self.assertRaisesRegex(ValueError,"STALE"): ValuationPriceService.validate_freshness(self.price,at=self.now+timedelta(minutes=6))
 def test_fx_direct_inverse_and_no_fabrication(self):
  FxValuationRate.objects.create(base_currency="USD",quote_currency="EUR",rate=Decimal("0.8"),rate_time=self.now,provider_id="fixture",source_ref="fx-1",quality_state="FRESH",policy_version="1")
  self.assertEqual(FxValuationService.resolve_rate("USD","EUR")[0],Decimal("0.8")); self.assertEqual(FxValuationService.resolve_rate("EUR","USD")[0],Decimal("1.25"))
  with self.assertRaises(ValueError): FxValuationService.resolve_rate("GBP","JPY")
 def test_position_unrealized_nav_and_performance_are_decimal(self):
  position=PositionValuationService.value_position(tenant_ref="tenant",account_ref=f"sim:{self.user.pk}",instrument_id="fixture-instrument",quantity=Decimal("2"),price=self.price,base_currency="USD")
  self.assertEqual(position.market_value,Decimal("200")); pnl=UnrealizedPnLService.calculate(valuation=position,remaining_cost_basis=Decimal("150")); self.assertEqual(pnl.unrealized_pnl,Decimal("50"))
  nav=PortfolioNavService.calculate(tenant_ref="tenant",account_ref=f"sim:{self.user.pk}",base_currency="USD",cash_value=Decimal("20"),position_value=Decimal("200")); self.assertEqual(nav.nav,Decimal("220"))
  perf=PerformanceReturnService.calculate_simple(tenant_ref="tenant",account_ref=f"sim:{self.user.pk}",period_start=self.now-timedelta(days=1),period_end=self.now,opening_value=Decimal("200"),closing_value=Decimal("220")); self.assertEqual(perf.return_value,Decimal("0.1"))
  with self.assertRaises(ValueError): PortfolioNavService.calculate(tenant_ref="t",account_ref="a",base_currency="USD",cash_value=20.0,position_value=Decimal("1"))
 def test_api_auth_and_tenant_scope(self):
  self.assertIn(APIClient().get("/api/v1/valuation/nav").status_code,(401,403))
  PortfolioNavService.calculate(tenant_ref="tenant",account_ref=f"sim:{self.user.pk}",base_currency="USD",cash_value=Decimal("1"),position_value=Decimal("2"))
  result=self.client.get("/api/v1/valuation/nav"); self.assertEqual(result.status_code,200); self.assertEqual(result.json()["results"][0]["nav"],"3.000000000000000000")
  self.assertEqual(self.client.get("/api/v1/valuation/prices/fixture-instrument").status_code,200)
 def test_unimplemented_authorities_fail_closed(self):
  self.assertEqual(self.client.get("/api/v1/valuation/positions").json()["code"],"FEATURE_DISABLED")
  self.assertEqual(self.client.get("/api/v1/valuation/reconciliation/status").status_code,503)
