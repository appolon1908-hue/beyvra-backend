from decimal import Decimal

from django.utils import timezone

from .common import POLICY_VERSION, audit
from .models import InstitutionalNavSnapshot, PortfolioNavSnapshot
from .positions import PositionValuationService


class PortfolioNavService:
    @classmethod
    def calculate(cls, *, tenant_ref, account_ref, base_currency="USD", cash_value=Decimal("0"), at=None):
        at = at or timezone.now()
        positions = PositionValuationService.value_portfolio(tenant_ref=tenant_ref, account_ref=account_ref, base_currency=base_currency, at=at)
        position_value = sum((p.base_currency_value for p in positions), Decimal("0"))
        assets = cash_value + max(position_value, Decimal("0"))
        liabilities = -min(position_value, Decimal("0"))
        row = PortfolioNavSnapshot.objects.create(tenant_ref=tenant_ref, account_ref=account_ref, base_currency=base_currency, cash_value=cash_value, position_value=position_value, receivables=0, payables=0, fees_accrued=0, total_assets=assets, total_liabilities=liabilities, nav=assets-liabilities, valuation_time=at, quality_state="FRESH", policy_version=POLICY_VERSION, simulation=True)
        audit(tenant_ref=tenant_ref, action="valuation.nav.generated", resource=row, evidence={"positions": len(positions), "nav": str(row.nav)})
        return row

    @staticmethod
    def get_snapshot(*, tenant_ref, account_ref):
        return PortfolioNavSnapshot.objects.filter(tenant_ref=tenant_ref, account_ref=account_ref).order_by("-valuation_time").first()


class InstitutionalNavService:
    @staticmethod
    def calculate(*, institution_ref, snapshots, adjustments=Decimal("0"), at=None):
        if not snapshots:
            raise ValueError("INSTITUTION_COMPONENTS_REQUIRED")
        currencies = {row.base_currency for row in snapshots}
        if len(currencies) != 1:
            raise ValueError("INSTITUTION_NAV_CURRENCY_MISMATCH")
        total = sum((row.nav for row in snapshots), Decimal("0"))
        return InstitutionalNavSnapshot.objects.create(institution_ref=institution_ref, base_currency=currencies.pop(), subaccount_nav_total=total, institution_level_adjustments=adjustments, nav=total + adjustments, valuation_time=at or timezone.now(), quality_state="FRESH", policy_version=POLICY_VERSION, simulation=True)

