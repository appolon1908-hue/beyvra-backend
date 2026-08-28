from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
import uuid

from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone
from rest_framework import permissions, views
from rest_framework.response import Response

from apps.trading.application.simulation import account_for, simulation_available
from apps.trading.models import SimulatedPosition, TradingOrder
from integrations.financial.simulated import SimulatedFinancialAdapter
from reference_data.models import Instrument

from .models import PerformanceSnapshot, ValuationPrice


ZERO = Decimal("0")
PERFORMANCE_WINDOWS = {
    "1D": timedelta(days=1),
    "1W": timedelta(days=7),
    "1M": timedelta(days=31),
    "3M": timedelta(days=93),
    "1Y": timedelta(days=366),
}


def _money(value):
    return str(Decimal(str(value)).quantize(Decimal("0.00000001")))


def _account_ref(request):
    return f"sim:{request.user.pk}"


def _instrument_metadata(instrument_id, instruments):
    instrument = instruments.get(str(instrument_id))
    if instrument is None:
        return {
            "symbol": instrument_id,
            "asset_class": "UNKNOWN",
            "currency": "USD",
            "venue": None,
        }
    return {
        "symbol": instrument.canonical_symbol,
        "asset_class": instrument.asset_class,
        "currency": instrument.currency,
        "venue": instrument.venue.code if instrument.venue else None,
    }


def _position_rows(account):
    latest_price = ValuationPrice.objects.filter(
        instrument_id=OuterRef("instrument_id"),
        quality_state__in=("FRESH", "CORRECTED"),
    ).order_by("-valuation_time")
    positions = list(
        SimulatedPosition.objects.filter(account=account)
        .annotate(
            selected_market_price=Subquery(latest_price.values("price")[:1]),
            selected_price_time=Subquery(latest_price.values("valuation_time")[:1]),
            selected_price_quality=Subquery(latest_price.values("quality_state")[:1]),
        )
        .order_by("instrument_id")
    )
    references = [str(position.instrument_id) for position in positions]
    symbol_references = []
    uuid_references = []
    for reference in references:
        try:
            uuid_references.append(uuid.UUID(reference))
        except (TypeError, ValueError):
            symbol_references.append(reference)

    instruments = {}
    symbol_matches = defaultdict(list)
    for instrument in Instrument.objects.filter(
        Q(canonical_symbol__in=symbol_references) | Q(instrument_id__in=uuid_references)
    ).select_related("venue"):
        instruments[str(instrument.instrument_id)] = instrument
        symbol_matches[instrument.canonical_symbol].append(instrument)
    for symbol, matches in symbol_matches.items():
        if len(matches) == 1:
            instruments[symbol] = matches[0]

    rows = []
    for position in positions:
        price = position.selected_market_price
        market_value = position.quantity * price if price is not None else None
        unrealized = (
            market_value - (position.quantity * position.average_price)
            if price is not None
            else None
        )
        rows.append(
            {
                "id": str(position.id),
                "instrument_id": position.instrument_id,
                **_instrument_metadata(position.instrument_id, instruments),
                "quantity": str(position.quantity),
                "average_entry_price": str(position.average_price),
                "market_price": str(price) if price is not None else None,
                "market_value": _money(market_value) if market_value is not None else None,
                "unrealized_pnl": _money(unrealized) if unrealized is not None else None,
                "realized_pnl": _money(position.realized_pnl),
                "price_as_of": (
                    position.selected_price_time.isoformat()
                    if position.selected_price_time
                    else None
                ),
                "price_quality": position.selected_price_quality or "UNAVAILABLE",
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


def _performance_range(request):
    range_name = request.query_params.get("range", "1M").upper()
    return range_name if range_name in {*PERFORMANCE_WINDOWS, "ALL"} else "1M"


def _performance_snapshots(request, range_name):
    rows = PerformanceSnapshot.objects.filter(
        account_ref=_account_ref(request)
    ).order_by("period_end")
    window = PERFORMANCE_WINDOWS.get(range_name)
    if window is not None:
        rows = rows.filter(period_end__gte=timezone.now() - window)
    return rows[:1000]


def _performance_quality(rows):
    if not rows:
        return "UNAVAILABLE"
    return (
        "COMPLETE"
        if all(row.quality_state in {"FRESH", "CORRECTED"} for row in rows)
        else "PARTIAL"
    )


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


class PortfolioPositionsView(PortfolioBaseView):
    def get(self, request):
        _account, positions, _available, _market_value, _unrealized, _realized = self.portfolio(request)
        return Response(
            {
                "results": positions,
                "count": len(positions),
                "unpriced_instruments": [
                    row["instrument_id"] for row in positions if row["market_value"] is None
                ],
                "quality": _valuation_quality(positions),
                "as_of": timezone.now().isoformat(),
                "simulation": True,
                "live_trading_enabled": False,
            }
        )


class PortfolioPerformanceView(PortfolioBaseView):
    def get(self, request):
        range_name = _performance_range(request)
        rows = list(_performance_snapshots(request, range_name))
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
                "quality": _performance_quality(rows),
                "reason": None if results else "PERFORMANCE_SNAPSHOTS_UNAVAILABLE",
                "as_of": rows[-1].period_end.isoformat() if rows else None,
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
        gross_exposure = sum((abs(value) for value in priced_values), ZERO)
        net_exposure = sum(priced_values, ZERO)
        largest = max((abs(value) for value in priced_values), default=ZERO)
        quality = _valuation_quality(positions)
        open_orders = TradingOrder.objects.filter(
            subject_ref=str(request.user.pk),
            tenant_ref="default",
            simulation=True,
            state__in=("PENDING", "ACCEPTED", "OPEN", "PARTIALLY_FILLED", "CANCEL_PENDING"),
        ).count()
        return Response(
            {
                "equity": _money(equity),
                "gross_exposure": _money(gross_exposure),
                "net_exposure": _money(net_exposure),
                "gross_exposure_ratio": str(gross_exposure / equity) if equity > 0 else None,
                "largest_position_ratio": str(largest / gross_exposure) if gross_exposure > 0 else None,
                "cash_ratio": str(available / equity) if equity > 0 else None,
                "open_orders": open_orders,
                "value_at_risk": None,
                "stress_loss": None,
                "advanced_risk_reason": "CERTIFIED_HISTORY_AND_POLICY_REQUIRED",
                "valuation_quality": quality,
                "methodology": {
                    "gross_exposure": "SUM_ABSOLUTE_PRICED_POSITION_MARKET_VALUE",
                    "net_exposure": "SUM_SIGNED_PRICED_POSITION_MARKET_VALUE",
                    "largest_position_ratio": "LARGEST_ABSOLUTE_POSITION_DIVIDED_BY_GROSS_EXPOSURE",
                    "cash_ratio": "AVAILABLE_SIMULATION_CASH_DIVIDED_BY_EQUITY",
                    "unpriced_positions_excluded": True,
                },
                "unavailable_metrics": [
                    {
                        "metric": "VALUE_AT_RISK",
                        "reason": "CERTIFIED_HISTORY_AND_POLICY_REQUIRED",
                    },
                    {
                        "metric": "STRESS_LOSS",
                        "reason": "APPROVED_SCENARIO_SET_AND_POLICY_REQUIRED",
                    },
                ],
                "simulation_available": simulation_available(),
                "simulation": True,
                "live_trading_enabled": False,
            }
        )


class PortfolioEvidenceQualityView(PortfolioBaseView):
    def get(self, request):
        _account, positions, _available, _market_value, _unrealized, _realized = self.portfolio(request)
        range_name = _performance_range(request)
        snapshots = list(_performance_snapshots(request, range_name))
        valuation_quality = _valuation_quality(positions)
        performance_quality = _performance_quality(snapshots)
        if valuation_quality == "EMPTY" and performance_quality == "UNAVAILABLE":
            overall_quality = "EMPTY"
        elif valuation_quality == "COMPLETE" and performance_quality == "COMPLETE":
            overall_quality = "COMPLETE"
        else:
            overall_quality = "PARTIAL"

        missing = []
        if valuation_quality in {"PARTIAL", "UNAVAILABLE"}:
            missing.append("CANONICAL_POSITION_VALUATIONS")
        if performance_quality == "UNAVAILABLE":
            missing.append("PERFORMANCE_HISTORY")
        missing.extend(("VALUE_AT_RISK_HISTORY_AND_POLICY", "APPROVED_STRESS_SCENARIOS"))

        return Response(
            {
                "overall_quality": overall_quality,
                "valuation": {
                    "quality": valuation_quality,
                    "position_count": len(positions),
                    "priced_position_count": sum(
                        row["market_value"] is not None for row in positions
                    ),
                    "unpriced_instruments": [
                        row["instrument_id"]
                        for row in positions
                        if row["market_value"] is None
                    ],
                },
                "performance": {
                    "quality": performance_quality,
                    "range": range_name,
                    "snapshot_count": len(snapshots),
                    "latest_snapshot_at": (
                        snapshots[-1].period_end.isoformat() if snapshots else None
                    ),
                },
                "advanced_risk": {
                    "quality": "UNAVAILABLE",
                    "reason": "CERTIFIED_HISTORY_AND_POLICY_REQUIRED",
                    "fabricated_values": False,
                },
                "missing_evidence": missing,
                "as_of": timezone.now().isoformat(),
                "simulation": True,
                "live_trading_enabled": False,
            }
        )
