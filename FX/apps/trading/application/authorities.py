"""Fail-closed canonical authorities used by PAPER order evaluation."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import uuid

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.trading.models import ExecutionProviderRecord
from pricing_authority.services import calculate_fee
from reference_data.models import Instrument, InstrumentVersion, MarketDataObservation, MarketStatusRecord


def decimal_input(value, *, field, allow_zero=False):
    raw = str(value)
    if not raw or len(raw) > 80 or "e" in raw.lower():
        raise ValueError(f"INVALID_{field.upper()}")
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"INVALID_{field.upper()}")
    if not parsed.is_finite() or parsed < 0 or (not allow_zero and parsed == 0):
        raise ValueError(f"INVALID_{field.upper()}")
    sign, digits, exponent = parsed.as_tuple()
    integer_digits = max(len(digits) + exponent, 0)
    decimal_places = max(-exponent, 0)
    if integer_digits + decimal_places > 36 or decimal_places > 18:
        raise ValueError(f"INVALID_{field.upper()}_PRECISION")
    return parsed


def _decimal_metadata(metadata, name):
    if name not in metadata:
        raise ValueError("INSTRUMENT_RULES_UNAVAILABLE")
    return decimal_input(metadata[name], field=name)


@dataclass(frozen=True)
class InstrumentRules:
    instrument: Instrument
    version: InstrumentVersion
    minimum_quantity: Decimal
    maximum_quantity: Decimal
    minimum_notional: Decimal
    maximum_notional: Decimal
    maximum_position: Decimal
    daily_notional_limit: Decimal
    daily_loss_limit: Decimal
    price_band_percent: Decimal

    @property
    def tick_size(self):
        return self.version.tick_size

    @property
    def lot_size(self):
        return self.version.lot_size


def resolve_instrument(reference, *, at=None):
    at = at or timezone.now()
    raw = str(reference or "").strip()
    if not raw:
        raise ValueError("INSTRUMENT_REQUIRED")
    try:
        instrument_id = uuid.UUID(raw)
    except (TypeError, ValueError, AttributeError):
        instrument_id = None
    candidates = Instrument.objects.select_related("calendar", "venue")
    if instrument_id is not None:
        instrument = candidates.filter(instrument_id=instrument_id).first()
        if instrument is None:
            raise ValueError("INSTRUMENT_UNAVAILABLE")
    else:
        matches = list(candidates.filter(canonical_symbol=raw.upper())[:2])
        if not matches:
            raise ValueError("INSTRUMENT_UNAVAILABLE")
        if len(matches) != 1:
            raise ValueError("INSTRUMENT_AMBIGUOUS")
        instrument = matches[0]
    if instrument.status != Instrument.Status.ACTIVE:
        raise ValueError("INSTRUMENT_UNAVAILABLE")
    versions = InstrumentVersion.objects.filter(
        instrument=instrument,
        effective_from__lte=at,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gt=at))
    if versions.count() != 1:
        raise ValueError("INSTRUMENT_RULES_UNAVAILABLE")
    version = versions.get()
    if version.status != Instrument.Status.ACTIVE:
        raise ValueError("INSTRUMENT_UNAVAILABLE")
    metadata = version.metadata or {}
    return InstrumentRules(
        instrument=instrument,
        version=version,
        minimum_quantity=_decimal_metadata(metadata, "minimum_quantity"),
        maximum_quantity=_decimal_metadata(metadata, "maximum_quantity"),
        minimum_notional=_decimal_metadata(metadata, "minimum_notional"),
        maximum_notional=_decimal_metadata(metadata, "maximum_notional"),
        maximum_position=_decimal_metadata(metadata, "maximum_position"),
        daily_notional_limit=_decimal_metadata(metadata, "daily_notional_limit"),
        daily_loss_limit=_decimal_metadata(metadata, "daily_loss_limit"),
        price_band_percent=_decimal_metadata(metadata, "price_band_percent"),
    )


def _multiple(value, increment):
    return value % increment == 0


def validate_instrument_values(rules, *, quantity, limit_price=None):
    if quantity < rules.minimum_quantity:
        raise ValueError("MIN_QUANTITY_NOT_MET")
    if quantity > rules.maximum_quantity:
        raise ValueError("MAX_QUANTITY_EXCEEDED")
    if not _multiple(quantity, rules.lot_size):
        raise ValueError("INVALID_LOT_SIZE")
    if limit_price is not None and not _multiple(limit_price, rules.tick_size):
        raise ValueError("INVALID_TICK_SIZE")


@dataclass(frozen=True)
class PriceEvidence:
    observation_id: uuid.UUID
    bid: Decimal
    ask: Decimal
    mid: Decimal
    observed_at: object
    stale_after: object
    provider_id: str
    provider_health: str

    def executable_price(self, side):
        return self.ask if side == "BUY" else self.bid


class MarketPriceAuthority:
    @staticmethod
    def observe(instrument, *, at=None):
        at = at or timezone.now()
        status = MarketStatusRecord.objects.filter(
            instrument=instrument,
            effective_at__lte=at,
        ).order_by("-effective_at", "-recorded_at").first()
        market_status = status.status if status else ("OPEN" if instrument.calendar.continuous else "UNKNOWN")
        if market_status != MarketStatusRecord.Status.OPEN:
            raise ValueError("MARKET_CLOSED")
        observation = MarketDataObservation.objects.filter(
            instrument=instrument,
            data_type="QUOTE",
            observed_at__lte=at,
        ).order_by("-observed_at", "-recorded_at").first()
        if observation is None:
            raise ValueError("PRICE_UNAVAILABLE")
        payload = observation.payload_safe or {}
        bid = decimal_input(payload.get("bid"), field="price")
        ask = decimal_input(payload.get("ask"), field="price")
        if ask < bid:
            raise ValueError("PRICE_INVALID")
        mid = decimal_input(payload.get("mid", (bid + ask) / Decimal("2")), field="price")
        stale_after = parse_datetime(str(payload.get("stale_after", "")))
        if stale_after is None:
            stale_after = observation.observed_at + timedelta(
                seconds=int(getattr(settings, "PAPER_PRICE_MAX_AGE_SECONDS", 30))
            )
        if stale_after <= at:
            raise ValueError("PRICE_STALE")
        provider = ExecutionProviderRecord.objects.filter(provider_id=observation.provider_id).first()
        if provider is None or not provider.enabled or provider.health != ExecutionProviderRecord.Health.HEALTHY:
            raise ValueError("PROVIDER_UNAVAILABLE")
        return PriceEvidence(
            observation_id=observation.observation_id,
            bid=bid,
            ask=ask,
            mid=mid,
            observed_at=observation.observed_at,
            stale_after=stale_after,
            provider_id=observation.provider_id,
            provider_health=provider.health,
        )


class FeeAuthority:
    @staticmethod
    def calculate(*, context, rules, side, order_type, quantity, notional, at=None):
        result = calculate_fee(
            account=context.user,
            fee_type="TRADING_COMMISSION",
            notional=notional,
            quantity=quantity,
            asset_class=rules.instrument.asset_class,
            instrument_ref=rules.instrument.instrument_id,
            venue_ref=rules.instrument.venue.code if rules.instrument.venue else "",
            side=side,
            order_type=order_type,
            at=at,
        )
        amount = result["amount"]
        return {
            "commission": amount,
            "spread_cost": Decimal("0"),
            "other_fees": Decimal("0"),
            "total": amount,
            "currency": result["currency"],
            "schedule_version": result["schedule_version"],
            "breakdown": result["breakdown"],
        }
