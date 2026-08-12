from decimal import Decimal

from django.utils import timezone

from .common import POLICY_VERSION
from .cost_basis import CostBasisService
from .models import UnrealizedPnLSnapshot
from .positions import PositionValuationService


class UnrealizedPnLService:
    @classmethod
    def calculate(cls, *, tenant_ref, account_ref, instrument_id, base_currency="USD", at=None):
        at = at or timezone.now()
        basis = CostBasisService.calculate(tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=instrument_id)
        value = PositionValuationService.value_position(tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=instrument_id, base_currency=base_currency, at=at)
        pnl = value.market_value - basis.total_cost_basis
        return UnrealizedPnLSnapshot.objects.create(tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=instrument_id, quantity=value.quantity, remaining_cost_basis=basis.total_cost_basis, market_value=value.market_value, unrealized_pnl=pnl, currency=value.price_currency, base_currency_pnl=value.base_currency_value - basis.total_cost_basis, valuation_time=at, quality_state=value.quality_state, policy_version=POLICY_VERSION)


class RealizedPnLService:
    @staticmethod
    def list_events(*, tenant_ref, account_ref):
        from .models import RealizedPnLEvent
        return RealizedPnLEvent.objects.filter(tenant_ref=tenant_ref, account_ref=account_ref).order_by("-realized_at")

