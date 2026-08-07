import os
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from fx_utils.models import TimeStampedModel
from wallet.models import Transaction, Wallet
from integrations.models import Organization


def validate_file_size(file_obj):
    filesize = file_obj.size
    kilobyte_limit = 512
    if filesize > kilobyte_limit * 1024:
        raise ValidationError("Max file size is %s KB" % str(kilobyte_limit))


def upload(instance, filename):
    return "/".join(["asset/images", f"{str(instance.name)}{os.path.splitext(filename)[1]}"])


class AssetType(TimeStampedModel):
    name = models.CharField(max_length=50, unique=True)  # e.g., 'Cryptocurrency', 'Stock', 'Commodity'

    def __str__(self):
        return self.name


class Asset(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)  # e.g., 'Bitcoin', 'Tesla Stock', 'Gold'
    asset_type = models.ForeignKey(AssetType, on_delete=models.CASCADE, related_name="assets")
    symbol = models.CharField(max_length=10, unique=True)  # e.g., 'BTC', 'TSLA', 'XAU'
    image = models.ImageField(
        upload_to=upload,
        blank=True,
        null=True,
        validators=[validate_file_size],
    )

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class MarketCandle(models.Model):
    symbol = models.CharField(max_length=32)
    interval = models.CharField(max_length=8, default="1m")
    timestamp = models.DateTimeField()
    open = models.DecimalField(max_digits=24, decimal_places=10)
    high = models.DecimalField(max_digits=24, decimal_places=10)
    low = models.DecimalField(max_digits=24, decimal_places=10)
    close = models.DecimalField(max_digits=24, decimal_places=10)
    volume = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    provider = models.CharField(max_length=32, default="binance")

    class Meta:
        ordering = ["timestamp"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "symbol", "interval", "timestamp"],
                name="unique_market_candle",
            )
        ]
        indexes = [
            models.Index(
                fields=["symbol", "interval", "-timestamp"],
                name="trade_marke_symbol_eb9c9d_idx",
            )
        ]


class TradeCategory(TimeStampedModel):
    name = models.CharField(max_length=20, unique=True)

    def __str__(self) -> str:
        return f"{self.name}"


class Trade(TimeStampedModel):
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="trades")
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="trades")
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="trades")
    quantity = models.DecimalField(max_digits=12, decimal_places=1)  # Quantity of the asset being traded
    price_per_unit = models.DecimalField(max_digits=12, decimal_places=4)  # Price per unit at the time of trade
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name="trade")
    trade_type = models.CharField(
        max_length=4,
        choices=[("buy", "buy"), ("sell", "sell"), ("up", "up"), ("down", "down")],
    )
    is_active = models.BooleanField(default=True)
    category = models.ForeignKey(TradeCategory, on_delete=models.RESTRICT, null=False, blank=False)
    duration = models.IntegerField(null=True, blank=False)  # duration in second
    result_time = models.DateTimeField(null=True)
    net = models.DecimalField(default=0, max_digits=12, decimal_places=4)
    open = models.DecimalField(default=0, max_digits=12, decimal_places=4)
    close = models.DecimalField(default=0, max_digits=12, decimal_places=4)
    demo_state = models.CharField(max_length=16, default="OPEN")
    demo_result = models.CharField(max_length=16, blank=True, default="")
    opening_price = models.DecimalField(max_digits=24, decimal_places=10, null=True, blank=True)
    closing_price = models.DecimalField(max_digits=24, decimal_places=10, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    payout = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    idempotency_key = models.CharField(max_length=255, null=True, blank=True, unique=True)

    def __str__(self):
        return f"{self.asset.symbol} {self.trade_type.capitalize()}"

    @property
    def total_value(self):
        return self.quantity * self.price_per_unit

    @property
    def percentage_change(self) -> Decimal:
        """
        Calculates the percentage change (gain or loss) for the trade.
        Returns:
            Decimal: Percentage change. Positive for gain, negative for loss.
        """
        if self.open != 0:
            # Ensure proper arithmetic with decimals
            change = ((Decimal(self.close) - Decimal(self.open)) / Decimal(self.open)) * 100
            # Round to 2 decimal places
            return round(change, 2)
        return Decimal("0.00")

    def clean(self):
        # Ensure quantity is greater than zero
        if self.quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")

        # Ensure price_per_unit is greater than zero
        if self.price_per_unit <= 0:
            raise ValidationError("Price per unit must be greater than zero.")

        # Ensure duration is > 0 for fixed time trades
        if self.category.name == "fixed" and self.duration <= 0:
            raise ValidationError("Duration can't be less than 1 sec, for fixed time trades.")

        # Ensure the trade type is correct for fixed time
        if self.category.name == "fixed" and not (self.trade_type == "up" or self.trade_type == "down"):
            raise ValidationError("Fixed time trade type can only be up or down.")

        # Ensure the trade type is correct not fixed time
        if self.category.name != "fixed" and (self.trade_type == "up" or self.trade_type == "down"):
            raise ValidationError("Only Fixed time trades can have the type up or down.")

    def save(self, *args, **kwargs):
        # Call clean to perform validation
        self.clean()
        # Proceed with saving the object
        super(Trade, self).save(*args, **kwargs)


class DemoLedgerEntry(TimeStampedModel):
    ENTRY_TYPES = (("INITIAL", "Initial demo credit"), ("RESERVE", "Trade reservation"), ("SETTLEMENT", "Trade settlement"), ("REFILL", "Demo refill"))
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="demo_ledger")
    trade = models.ForeignKey(Trade, null=True, blank=True, on_delete=models.SET_NULL, related_name="ledger_entries")
    entry_type = models.CharField(max_length=16, choices=ENTRY_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    idempotency_key = models.CharField(max_length=255, unique=True)
    description = models.CharField(max_length=255, blank=True)


class DemoEventOutbox(models.Model):
    """Transactional, account-scoped demo event awaiting JetStream publish."""

    sequence = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event_type = models.CharField(max_length=64)
    event_version = models.PositiveSmallIntegerField(default=1)
    channel = models.CharField(max_length=96)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="demo_event_outbox")
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="demo_event_outbox")
    trade = models.ForeignKey(Trade, null=True, blank=True, on_delete=models.PROTECT, related_name="demo_events")
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(default=models.functions.Now)
    published_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("next_attempt_at", "sequence"),
                condition=models.Q(published_at__isnull=True),
                name="demo_outbox_pending_idx",
            ),
            models.Index(fields=("wallet", "sequence"), name="demo_outbox_account_idx"),
        ]
