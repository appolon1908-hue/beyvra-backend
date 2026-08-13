import os
from django.core.exceptions import ValidationError
from django.db import models
from users.models import User
from uuid import uuid4
from decimal import Decimal
from .utils import ExchangeRateService
from integrations.models import Organization

def validate_file_size(file_obj):
    filesize = file_obj.size
    kilobyte_limit = 512
    if filesize > kilobyte_limit * 1024:
        raise ValidationError("Max file size is %s KB" % str(kilobyte_limit))


def upload(instance, filename):
    return "/".join(["currency/images", f"{str(instance.name)}{os.path.splitext(filename)[1]}"])


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Currency(TimeStampedModel):
    name = models.CharField(max_length=30, blank=False, null=False, unique=True)
    symbol = models.CharField(max_length=5, blank=False, null=False, unique=True)
    longer_name = models.CharField(max_length=50, blank=False, null=False, unique=True)
    image = models.ImageField(
        upload_to=upload,
        blank=True,
        null=True,
        validators=[validate_file_size],
    )
    is_crypto = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Wallet(TimeStampedModel):
    name = models.CharField(max_length=25, null=False, blank=False)
    currency = models.ForeignKey(Currency, blank=False, null=False, on_delete=models.RESTRICT)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="wallets")
    balance = models.DecimalField(blank=False, null=False, decimal_places=2, max_digits=12, default=0)
    is_active = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    # Application-created wallets are demo-only unless explicitly marked.
    # Real balances remain Financial Service authoritative.
    is_real = models.BooleanField(default=False)

    class Meta:
        unique_together = ["user", "organization", "name"]

    def __str__(self):
        return f"{self.user}-{self.name}"
    
    def credit(self, amount, currency):
        """
        Add funds to the wallet. Converts amount to wallet's currency if needed.
        """
        if self.is_real:
            raise ValidationError("FEATURE_DISABLED: real balances are Financial Service authoritative")
        rate = ExchangeRateService().get_rate(currency, self.currency)
        if rate is None:
            # Handle the case where the exchange rate is not available
            raise ValueError(f"Unable to get exchange rate for {currency} to {self.currency}")

        converted_amount = amount * Decimal(rate)
        self.balance += converted_amount
        self.save()

    def debit(self, amount, currency):
        """
        Subtract funds from the wallet. Converts amount to wallet's currency if needed.
        """
        if self.is_real:
            raise ValidationError("FEATURE_DISABLED: real balances are Financial Service authoritative")
        rate = ExchangeRateService().get_rate(currency, self.currency)
        if rate is None:
            # Handle the case where the exchange rate is not available
            raise ValueError(f"Unable to get exchange rate for {currency} to {self.currency}")

        converted_amount = amount * Decimal(rate)
        if converted_amount > self.balance:
            raise ValueError("Insufficient balance")
        self.balance -= converted_amount
        self.save()


class Transaction(TimeStampedModel):
    TYPE_CHOICES = (
        ("D", "DEPOSIT"),
        ("W", "WITHDRAWAL"),
        ("TD", "TRADE"),
        ("TN", "TRANSFER"),
    )
    STATUS_CHOICES = (
        ("P", "PENDING"),
        ("S", "SUCCESSFUL"),
        ("F", "FAILED"),
        ("R", "REFUNDED"),
    )
    transaction_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.RESTRICT)
    type = models.CharField(choices=TYPE_CHOICES)
    amount = models.DecimalField(blank=False, null=False, decimal_places=2, max_digits=12)
    status = models.CharField(choices=STATUS_CHOICES)
    gateway = models.CharField(max_length=20, null=True, blank=True)
    reference = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.type} - {self.amount} {self.wallet.currency}"



class ManualBalanceUpdate(TimeStampedModel):
    REASON_CHOICES = [
        ('CORRECTION', 'Correction'),
        ('BONUS', 'Bonus'),
        ('FEE', 'Fee Deduction'),
        ('OTHER', 'Other'),
    ]

    admin = models.ForeignKey(User, on_delete=models.CASCADE)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE)
    previous_balance = models.DecimalField(max_digits=20, decimal_places=2)
    new_balance = models.DecimalField(max_digits=20, decimal_places=2)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.admin} updated balance from {self.previous_balance} to {self.new_balance} for {self.wallet} on {self.created_at}"

    class Meta:
        ordering = ['-created_at']
