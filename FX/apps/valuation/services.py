from decimal import Decimal
from django.utils import timezone
from .common import POLICY_VERSION
from .fx import FxValuationService
from .models import PerformanceSnapshot, PortfolioNavSnapshot, PositionValuation, UnrealizedPnLSnapshot


def decimal(value, name):
    if not isinstance(value, Decimal) or not value.is_finite(): raise ValueError(f"{name} must be Decimal")
    return value


class PositionValuationService:
    @classmethod
    def value_position(cls, *, tenant_ref, account_ref, instrument_id, quantity, price, base_currency, multiplier=Decimal("1")):
        quantity=decimal(quantity,"quantity"); multiplier=decimal(multiplier,"multiplier")
        market=quantity*price.price*multiplier
        converted, refs, _=FxValuationService.convert(market,price.currency,base_currency,at=price.valuation_time)
        return PositionValuation.objects.create(tenant_ref=tenant_ref,account_ref=account_ref,instrument_id=instrument_id,quantity=quantity,valuation_price=price.price,price_currency=price.currency,market_value=market,base_currency_value=converted,valuation_time=price.valuation_time,price_ref=price,fx_ref=refs[0] if refs else None,quality_state=price.quality_state,policy_version=POLICY_VERSION,simulation=True)
    value_portfolio=value_position


class UnrealizedPnLService:
    @staticmethod
    def calculate(*, valuation, remaining_cost_basis):
        basis=decimal(remaining_cost_basis,"remaining_cost_basis"); pnl=valuation.market_value-basis
        return UnrealizedPnLSnapshot.objects.create(tenant_ref=valuation.tenant_ref,account_ref=valuation.account_ref,instrument_id=valuation.instrument_id,quantity=valuation.quantity,remaining_cost_basis=basis,market_value=valuation.market_value,unrealized_pnl=pnl,currency=valuation.price_currency,base_currency_pnl=pnl,valuation_time=valuation.valuation_time,quality_state=valuation.quality_state,policy_version=POLICY_VERSION)


class PortfolioNavService:
    @staticmethod
    def calculate(*, tenant_ref, account_ref, base_currency, cash_value, position_value, receivables=Decimal("0"), payables=Decimal("0"), fees_accrued=Decimal("0"), at=None):
        values=[decimal(x,"nav component") for x in (cash_value,position_value,receivables,payables,fees_accrued)]
        assets=values[0]+values[1]+values[2]; liabilities=values[3]+values[4]
        return PortfolioNavSnapshot.objects.create(tenant_ref=tenant_ref,account_ref=account_ref,base_currency=base_currency,cash_value=values[0],position_value=values[1],receivables=values[2],payables=values[3],fees_accrued=values[4],total_assets=assets,total_liabilities=liabilities,nav=assets-liabilities,valuation_time=at or timezone.now(),quality_state="FRESH",policy_version=POLICY_VERSION,simulation=True)
    get_snapshot=calculate


class PerformanceReturnService:
    @staticmethod
    def calculate_simple(*, tenant_ref, account_ref, period_start, period_end, opening_value, closing_value, external_flows=Decimal("0"), income=Decimal("0"), fees=Decimal("0")):
        opening=decimal(opening_value,"opening"); closing=decimal(closing_value,"closing"); flows=decimal(external_flows,"flows")
        if opening<=0: raise ValueError("PERFORMANCE_OPENING_VALUE_INVALID")
        pnl=closing-opening-flows; result=pnl/opening
        return PerformanceSnapshot.objects.create(tenant_ref=tenant_ref,account_ref=account_ref,period_start=period_start,period_end=period_end,opening_value=opening,closing_value=closing,external_flows=flows,income=income,fees=fees,pnl=pnl,return_value=result,return_method="SIMPLE_RETURN",quality_state="FRESH",policy_version=POLICY_VERSION)
