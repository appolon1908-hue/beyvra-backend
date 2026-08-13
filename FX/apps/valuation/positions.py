from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.post_trade.models import TradePositionEffect

from .common import POLICY_VERSION, audit
from .fx import FxValuationService
from .models import PositionValuation
from .prices import ValuationPriceService


class PositionValuationService:
    @classmethod
    def quantity(cls, *, tenant_ref, account_ref, instrument_id):
        return TradePositionEffect.objects.filter(trade__tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=instrument_id).aggregate(v=Sum("quantity_delta"))["v"] or Decimal("0")

    @classmethod
    def value_position(cls, *, tenant_ref, account_ref, instrument_id, base_currency="USD", at=None, purpose="INTRADAY"):
        at = at or timezone.now()
        quantity = cls.quantity(tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=instrument_id)
        price = ValuationPriceService.resolve(instrument_id, purpose=purpose, at=at)
        market_value = quantity * price.price
        base_value, refs, _ = FxValuationService.convert(market_value, price.currency, base_currency, at=at)
        row = PositionValuation.objects.create(tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=instrument_id, quantity=quantity, valuation_price=price.price, price_currency=price.currency, market_value=market_value, base_currency_value=base_value, valuation_time=at, price_ref=price, fx_ref=refs[0] if refs else None, quality_state=price.quality_state, policy_version=POLICY_VERSION, simulation=True)
        audit(tenant_ref=tenant_ref, action="valuation.position.valued", resource=row, evidence={"price_ref": str(price.id), "quantity": str(quantity), "base_value": str(base_value)})
        return row

    @classmethod
    def value_portfolio(cls, *, tenant_ref, account_ref, base_currency="USD", at=None):
        instruments = TradePositionEffect.objects.filter(trade__tenant_ref=tenant_ref, account_ref=account_ref).values_list("instrument_id", flat=True).distinct()
        return [cls.value_position(tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=i, base_currency=base_currency, at=at) for i in instruments if cls.quantity(tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=i)]

