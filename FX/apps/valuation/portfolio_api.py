from collections import defaultdict
from decimal import Decimal
import uuid

from django.utils import timezone
from rest_framework import permissions, views
from rest_framework.response import Response

from apps.trading.application.simulation import account_for, simulation_available
from apps.trading.models import SimulatedPosition, TradingOrder
from integrations.financial.simulated import SimulatedFinancialAdapter
from reference_data.models import Instrument

from .models import PerformanceSnapshot, ValuationPrice


ZERO = Decimal("0")


def _money(value):
    return str(value.quantize(Decimal("0.00000001")))


def _account_ref(request):
    return f"sim:{request.user.pk}"


def _instrument_metadata(instrument_id):
    by_symbol = Instrument.objects.filter(canonical_symbol=instrument_id).select_related("venue").first()
    if by_symbol is None:
        try:
            parsed_id = uuid.UUID(str(instrument_id))
        except (TypeError, ValueError):
            parsed_id = None
        if parsed_id is not None:
            by_symbol = Instrument.objects.filter(instrument_id=parsed_id).select_related("venue").first()
    if by_symbol is None:
        return {"symbol": instrument_id, "asset_class": "UNKNOWN", "currency": "USD", "venue": None}
    return {
        "symbol": by_symbol.canonical_symbol,
        "asset_class": by_symbol.asset_class,
        "currency": by_symbol.currency,
        "venue": by_symbol.venue.code if by_symbol.venue else None,
    }


def _position_rows(account):
    rows = []
    for position in SimulatedPosition.objects.filter(account=account).order_by("instrument_id"):
        price = ValuationPrice.objects.filter(
            instrument_id=position.instrument_id,
            quality_state__in=("FRESH", "CORRECTED"),
        ).order_by("-valuation_time").first()
        market_value = position.quantity * price.price if price else None
        unrealized = market_value - (position.quantity * position.average_price) if price else None
        rows.append(
            {
                "id": str(position.id),
                "instrument_id": position.instrument_id,
                **_instrument_metadata(position.instrument_id),
                "quantity": str(position.quantity),
                "average_entry_price": str(position.average_price),
                "market_price": str(price.price) if price else None,
                "market_value": _money(market_value) if market_value is not None else None,
                "unrealized_pnl": _money(unrealized) if unrealized is not None else None,
                "realized_pnl": _money(position.realized_pnl),
                "price_as_of": price.valuation_time.isoformat() if price else None,
                "price_quality": price.quality_state if price else "UNAVAILABLE",
                "simulation": True,
            }
        )
    return rows


def _valuation_quality(positions):
    if not positions:
        return "EMPTY"
    priced = sum(row["market_value"] is not None for row in positions)
    if priced == len(positions):
        return "COMPLETE"
    return "PARTIAL" if priced else "UNAVAILABLE"


class PortfolioBaseView(views.APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def portfolio(self, request):
        account = account_for(request.user)
        positions = _position_rows(account)
        available = SimulatedFinancialAdapter.available_quote(account)
        market_value = sum(
            (Decimal(row["market_value"]) for row in positions if row["market_value"] is not None),
            ZERO,
        )
        unrealized = sum(
            (Decimal(row["unrealized_pnl"]) for row in positions if row["unrealized_pnl"] is not None),
            ZERO,
        )
        realized = sum((Decimal(row["realized_pnl"]) for row in positions), ZERO)
        return account, positions, available, market_value, unrealized, realized


class PortfolioSummaryView(PortfolioBaseView):
    def get(self, request):
        account, positions, available, market_value, unrealized, realized = self.portfolio(request)
        return Response(
            {
                "account_id": str(account.id),
                "base_currency": account.quote_currency,
                "cash": _money(account.total_balance),
                "available_cash": _money(available),
                "reserved_cash": _money(account.total_balance - account.pending_balance - available),
                "market_value": _money(market_value),
                "equity": _money(account.total_balance + market_value),
                "unrealized_pnl": _money(unrealized),
                "realized_pnl": _money(realized),
                "positions": positions,
                "valuation_quality": _valuation_quality(positions),
                "as_of": timezone.now().isoformat(),
                "simulation": True,
                "live_trading_enabled": False,
            }
        )


class PortfolioPerformanceView(PortfolioBaseView):
    def get(self, request):
        range_name = request.query_params.get("range", "1M").upper()
        allowed_ranges = {"1D", "1W", "1M", "3M", "1Y", "ALL"}
        if range_name not in allowed_ranges:
            range_name = "1M"
        rows = PerformanceSnapshot.objects.filter(account_ref=_account_ref(request)).order_by("period_end")[:1000]
        results = [
            {
                "period_start": row.period_start.isoformat(),
                "period_end": row.period_end.isoformat(),
                "opening_value": _money(row.opening_value),
                "closing_value": _money(row.closing_value),
                "pnl": _money(row.pnl),
                "return": str(row.return_value),
                "quality": row.quality_state,
            }
            for row in rows
        ]
        return Response(
            {
                "range": range_name,
                "currency": "USD",
                "results": results,
                "quality": "COMPLETE" if results else "UNAVAILABLE",
                "reason": None if results else "PERFORMANCE_SNAPSHOTS_UNAVAILABLE",
                "simulation": True,
            }
        )


class PortfolioAllocationsView(PortfolioBaseView):
    def get(self, request):
        _account, positions, _available, market_value, _unrealized, _realized = self.portfolio(request)
        buckets = defaultdict(Decimal)
        unpriced = []
        for row in positions:
            if row["market_value"] is None:
                unpriced.append(row["instrument_id"])
            else:
                buckets[row["asset_class"]] += Decimal(row["market_value"])
        results = [
            {
                "asset_class": asset_class,
                "market_value": _money(value),
                "weight": str(value / market_value) if market_value else None,
            }
            for asset_class, value in sorted(buckets.items())
        ]
        return Response(
            {
                "currency": "USD",
                "results": results,
                "unpriced_instruments": unpriced,
                "quality": _valuation_quality(positions),
                "simulation": True,
            }
        )


class PortfolioRiskView(PortfolioBaseView):
    def get(self, request):
        account, positions, available, market_value, _unrealized, _realized = self.portfolio(request)
        equity = account.total_balance + market_value
        priced_values = [Decimal(row["market_value"]) for row in positions if row["market_value"] is not None]
        largest = max(priced_values, default=ZERO)
        open_orders = TradingOrder.objects.filter(
            subject_ref=str(request.user.pk),
            tenant_ref="default",
            simulation=True,
            state__in=("PENDING", "ACCEPTED", "OPEN", "PARTIALLY_FILLED", "CANCEL_PENDING"),
        ).count()
        return Response(
            {
                "equity": _money(equity),
                "gross_exposure": _money(market_value),
                "gross_exposure_ratio": str(market_value / equity) if equity > 0 else None,
                "largest_position_ratio": str(largest / market_value) if market_value > 0 else None,
                "cash_ratio": str(available / equity) if equity > 0 else None,
                "open_orders": open_orders,
                "value_at_risk": None,
                "stress_loss": None,
                "advanced_risk_reason": "CERTIFIED_HISTORY_AND_POLICY_REQUIRED",
                "valuation_quality": _valuation_quality(positions),
                "simulation_available": simulation_available(),
                "simulation": True,
                "live_trading_enabled": False,
            }
        )
