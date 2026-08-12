import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Venue(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=160)
    mic = models.CharField(max_length=4, blank=True, db_index=True)
    timezone = models.CharField(max_length=64, default="UTC")
    country_code = models.CharField(max_length=2, blank=True)
    active = models.BooleanField(default=True)


class TradingCalendar(models.Model):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=160)
    timezone = models.CharField(max_length=64)
    continuous = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)


class CalendarSession(models.Model):
    class Kind(models.TextChoices):
        REGULAR = "REGULAR"
        EARLY_CLOSE = "EARLY_CLOSE"
        CLOSED = "CLOSED"
        AUCTION = "AUCTION"

    calendar = models.ForeignKey(TradingCalendar, on_delete=models.PROTECT, related_name="sessions")
    session_date = models.DateField()
    kind = models.CharField(max_length=16, choices=Kind.choices)
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=160, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("calendar", "session_date", "kind"), name="reference_calendar_session_identity")]
        ordering = ("session_date", "opens_at")

    def clean(self):
        if self.kind == self.Kind.CLOSED and (self.opens_at or self.closes_at):
            raise ValidationError("Closed sessions cannot have open or close timestamps.")
        if self.kind != self.Kind.CLOSED and (not self.opens_at or not self.closes_at or self.opens_at >= self.closes_at):
            raise ValidationError("Open sessions require an increasing open/close interval.")


class Instrument(models.Model):
    class AssetClass(models.TextChoices):
        EQUITY = "EQUITY"
        ETF = "ETF"
        CRYPTO = "CRYPTO"
        FX = "FX"
        FUTURE = "FUTURE"
        OPTION = "OPTION"
        BOND = "BOND"
        COMMODITY = "COMMODITY"
        INDEX = "INDEX"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        HALTED = "HALTED"
        DELISTED = "DELISTED"
        EXPIRED = "EXPIRED"
        INACTIVE = "INACTIVE"

    instrument_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    canonical_symbol = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    asset_class = models.CharField(max_length=16, choices=AssetClass.choices)
    currency = models.CharField(max_length=12)
    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, related_name="instruments", null=True, blank=True)
    calendar = models.ForeignKey(TradingCalendar, on_delete=models.PROTECT, related_name="instruments")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    isin = models.CharField(max_length=12, blank=True, db_index=True)
    cusip = models.CharField(max_length=9, blank=True, db_index=True)
    figi = models.CharField(max_length=12, blank=True, db_index=True)
    tick_size = models.DecimalField(max_digits=30, decimal_places=12)
    lot_size = models.DecimalField(max_digits=30, decimal_places=12)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("canonical_symbol", "venue"), name="reference_canonical_symbol_venue"),
            models.UniqueConstraint(fields=("canonical_symbol",), condition=Q(venue__isnull=True), name="reference_otc_canonical_symbol"),
            models.UniqueConstraint(fields=("isin",), condition=~Q(isin=""), name="reference_unique_isin"),
            models.UniqueConstraint(fields=("cusip",), condition=~Q(cusip=""), name="reference_unique_cusip"),
            models.UniqueConstraint(fields=("figi",), condition=~Q(figi=""), name="reference_unique_figi"),
            models.CheckConstraint(condition=Q(tick_size__gt=0), name="reference_positive_tick_size"),
            models.CheckConstraint(condition=Q(lot_size__gt=0), name="reference_positive_lot_size"),
        ]
        ordering = ("canonical_symbol",)


class InstrumentVersion(models.Model):
    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    canonical_symbol = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=16, choices=Instrument.Status.choices)
    tick_size = models.DecimalField(max_digits=30, decimal_places=12)
    lot_size = models.DecimalField(max_digits=30, decimal_places=12)
    metadata = models.JSONField(default=dict, blank=True)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("instrument", "version"), name="reference_instrument_version"),
            models.UniqueConstraint(fields=("instrument",), condition=Q(effective_to__isnull=True), name="reference_one_current_instrument_version"),
        ]
        ordering = ("instrument_id", "effective_from")

    def clean(self):
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValidationError("effective_to must be later than effective_from.")


class ProviderSymbolMapping(models.Model):
    provider_id = models.CharField(max_length=64)
    provider_symbol = models.CharField(max_length=128)
    product = models.CharField(max_length=64, default="MARKET_DATA")
    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name="provider_mappings")
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("provider_id", "product", "provider_symbol", "effective_from"), name="reference_provider_mapping_identity"),
            models.UniqueConstraint(fields=("provider_id", "product", "provider_symbol"), condition=Q(effective_to__isnull=True), name="reference_one_current_provider_symbol"),
        ]
        indexes = [models.Index(fields=("provider_id", "product", "provider_symbol", "effective_from"), name="reference_provider_lookup")]

    def clean(self):
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValidationError("effective_to must be later than effective_from.")


class CorporateAction(models.Model):
    class Type(models.TextChoices):
        SPLIT = "SPLIT"
        DIVIDEND = "DIVIDEND"
        MERGER = "MERGER"
        SYMBOL_CHANGE = "SYMBOL_CHANGE"
        DELISTING = "DELISTING"
        TOKEN_MIGRATION = "TOKEN_MIGRATION"
        FORK = "FORK"
        EXPIRY = "EXPIRY"
        ROLL = "ROLL"
        EXERCISE = "EXERCISE"
        ASSIGNMENT = "ASSIGNMENT"

    action_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name="corporate_actions")
    action_type = models.CharField(max_length=24, choices=Type.choices)
    announced_at = models.DateTimeField()
    effective_at = models.DateTimeField()
    source_provider = models.CharField(max_length=64)
    source_reference = models.CharField(max_length=160)
    terms = models.JSONField(default=dict)
    supersedes = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="corrections")
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("source_provider", "source_reference"), name="reference_corporate_action_source")]
        ordering = ("effective_at",)

    def clean(self):
        if self.effective_at < self.announced_at:
            raise ValidationError("Corporate action cannot be effective before announcement.")
        required = {
            self.Type.SPLIT: {"ratio_from", "ratio_to"},
            self.Type.DIVIDEND: {"amount", "currency"},
            self.Type.SYMBOL_CHANGE: {"new_symbol"},
            self.Type.MERGER: {"target_instrument_id"},
        }.get(self.action_type, set())
        if required - set(self.terms):
            raise ValidationError("Corporate action terms are incomplete.")


class MarketStatusRecord(models.Model):
    class Status(models.TextChoices):
        PREOPEN = "PREOPEN"
        OPEN = "OPEN"
        AUCTION = "AUCTION"
        HALTED = "HALTED"
        CLOSED = "CLOSED"
        UNKNOWN = "UNKNOWN"

    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name="market_status_records")
    status = models.CharField(max_length=16, choices=Status.choices)
    effective_at = models.DateTimeField()
    observed_at = models.DateTimeField()
    source_provider = models.CharField(max_length=64)
    source_reference = models.CharField(max_length=160)
    reason = models.CharField(max_length=160, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("source_provider", "source_reference"), name="reference_market_status_source")]
        ordering = ("instrument_id", "-effective_at")


class MarketDataObservation(models.Model):
    observation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name="market_observations")
    provider_id = models.CharField(max_length=64)
    provider_symbol = models.CharField(max_length=128)
    data_type = models.CharField(max_length=32)
    provider_event_id = models.CharField(max_length=160)
    observed_at = models.DateTimeField()
    received_at = models.DateTimeField()
    payload_hash = models.CharField(max_length=64)
    payload_safe = models.JSONField(default=dict)
    mapping = models.ForeignKey(ProviderSymbolMapping, on_delete=models.PROTECT)
    supersedes = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="corrections")
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("provider_id", "data_type", "provider_event_id"), name="reference_market_observation_source")]
        ordering = ("instrument_id", "observed_at", "recorded_at")


class ReferenceDataAudit(models.Model):
    audit_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=64)
    entity_ref = models.CharField(max_length=160)
    actor_ref = models.CharField(max_length=160, default="system")
    occurred_at = models.DateTimeField()
    evidence_hash = models.CharField(max_length=64)
    metadata_safe = models.JSONField(default=dict)

    class Meta:
        ordering = ("occurred_at", "audit_id")
