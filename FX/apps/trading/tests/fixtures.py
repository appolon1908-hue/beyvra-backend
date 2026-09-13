"""Explicit canonical PAPER authorities, independent of migration seed history."""

from datetime import date, datetime, timedelta, timezone as datetime_timezone

from apps.post_trade.models import SettlementCalendar
from apps.trading.execution_control.capabilities import seed_fixture_capabilities
from apps.trading.models import ExecutionProviderRecord
from django.utils import timezone
from pricing_authority.models import FeeRule, FeeSchedule, PricingRoundingPolicy
from reference_data.models import Instrument, InstrumentVersion, ProviderSymbolMapping, TradingCalendar
from reference_data.services import record_market_observation


def ensure_paper_settlement_calendar():
    calendar = SettlementCalendar.objects.get_or_create(
        code="TEST-PAPER-CRYPTO-INSTANT",
        policy_version="paper-test-v1",
        defaults={
            "asset_class": "CRYPTO",
            "venue_id": "SIMULATED",
            "currency": "USD",
            "settlement_convention": "INSTANT",
            "timezone": "UTC",
            "calendar_ref": "TEST_PAPER_24X7",
            "holidays": [],
            "effective_from": date(2020, 1, 1),
        },
    )[0]
    now = timezone.now()
    trading_calendar, _ = TradingCalendar.objects.get_or_create(
        code="TEST-PAPER-24X7",
        defaults={"name": "Test PAPER continuous", "timezone": "UTC", "continuous": True},
    )
    instrument, _ = Instrument.objects.get_or_create(
        canonical_symbol="BTC-USD",
        venue=None,
        defaults={
            "name": "Bitcoin / US Dollar PAPER",
            "asset_class": Instrument.AssetClass.CRYPTO,
            "currency": "USD",
            "calendar": trading_calendar,
            "status": Instrument.Status.ACTIVE,
            "tick_size": "0.01",
            "lot_size": "0.0001",
        },
    )
    InstrumentVersion.objects.get_or_create(
        instrument=instrument,
        version=1,
        defaults={
            "canonical_symbol": instrument.canonical_symbol,
            "name": instrument.name,
            "status": Instrument.Status.ACTIVE,
            "tick_size": "0.01",
            "lot_size": "0.0001",
            "metadata": {
                "minimum_quantity": "0.0001",
                "maximum_quantity": "100",
                "minimum_notional": "1",
                "maximum_notional": "1000000",
                "maximum_position": "100",
                "daily_notional_limit": "1000000",
                "daily_loss_limit": "10000",
                "price_band_percent": "5",
            },
            "effective_from": now - timedelta(days=1),
        },
    )
    mapping, _ = ProviderSymbolMapping.objects.get_or_create(
        provider_id="paper-market",
        product="MARKET_DATA",
        provider_symbol="BTC-USD",
        defaults={"instrument": instrument, "effective_from": now - timedelta(days=1)},
    )
    ExecutionProviderRecord.objects.update_or_create(
        provider_id="paper-market",
        defaults={
            "display_name": "Canonical PAPER market authority",
            "provider_type": "MARKET_DATA",
            "environment": "SIMULATION",
            "mode": "SIMULATION",
            "governance_state": "PAPER_APPROVED",
            "paper_supported": True,
            "enabled": True,
            "health": "HEALTHY",
            "supported_asset_classes": ["CRYPTO"],
            "supported_order_types": [],
            "supported_venues": [],
            "capabilities": {"pricing": True, "network": False},
        },
    )
    record_market_observation(
        provider_id=mapping.provider_id,
        provider_symbol=mapping.provider_symbol,
        data_type="QUOTE",
        provider_event_id=f"paper-quote-{timezone.now().timestamp()}",
        observed_at=now,
        payload_safe={
            "bid": "99.00",
            "ask": "100.00",
            "mid": "99.50",
            "stale_after": (now + timedelta(hours=1)).isoformat(),
        },
    )
    fee_schedule, _ = FeeSchedule.objects.get_or_create(
        code="PAPER-TRADING-COMMISSION-V1",
        defaults={
            "name": "PAPER trading commission",
            "fee_type": "TRADING_COMMISSION",
            "status": "ACTIVE",
            "currency": "USD",
            "effective_from": now - timedelta(days=1),
            "priority": 1,
        },
    )
    FeeRule.objects.get_or_create(
        schedule=fee_schedule,
        asset_class="CRYPTO",
        rule_version=1,
        defaults={
            "rate_type": "BASIS_POINTS",
            "rate_value": "10",
            "currency": "USD",
            "effective_from": now - timedelta(days=1),
        },
    )
    PricingRoundingPolicy.objects.get_or_create(
        currency="USD",
        effective_from=datetime(2020, 1, 1, tzinfo=datetime_timezone.utc),
        defaults={"decimal_places": 2, "rounding_mode": "ROUND_HALF_UP"},
    )
    seed_fixture_capabilities()
    return calendar
