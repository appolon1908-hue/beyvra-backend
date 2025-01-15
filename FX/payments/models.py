import os

from django.core.exceptions import ValidationError
from django.db import models
from fx_utils.models import TimeStampedModel
from users.models import User
from wallet.models import Wallet
from wallet.models import Currency
from uuid import uuid4


def validate_file_size(file_obj):
    filesize = file_obj.size
    kilobyte_limit = 512
    if filesize > kilobyte_limit * 1024:
        raise ValidationError("Max file size is %s KB" % str(kilobyte_limit))


def upload(instance, filename):
    return "/".join(["payment/icons", f"{str(instance.name)}{os.path.splitext(filename)[1]}"])


class PaymentsProvider(models.Model):
    name = models.CharField(max_length=100)
    fiat_option = models.BooleanField(default=False)
    crypto_option = models.BooleanField(default=False)
    epayment_option = models.BooleanField(default=False)
    website_url = models.URLField(max_length=200, blank=True, null=True)
    supported_currencies = models.ManyToManyField(Currency, related_name="currencies")

    def __str__(self):
        return self.name


class PaymentMethod(TimeStampedModel):
    TYPE_CHOICES = (
        ("bank", "bank"),
        ("epayment", "epayment"),
        ("crypto", "crypto"),
    )
    name = models.CharField(max_length=50, unique=True)
    type = models.CharField(choices=TYPE_CHOICES)
    icon = models.FileField(
        upload_to=upload,
        blank=True,
        null=True,
        validators=[validate_file_size],
    )
    account_id = models.CharField(max_length=100)
    network = models.CharField(max_length=50, null=True, blank=True)
    is_active = models.BooleanField(default=True)


class Payment(models.Model):
    TYPE_CHOICES = [
        ('Deposit', 'Deposit'),
        ('Withdrawal', 'Withdrawal'),
    ]
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled'),
        ('In Progress', 'In Progress'),
    ]
    payment_id = models.UUIDField(default=uuid4, editable=False, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    provider = models.ForeignKey(PaymentsProvider, on_delete=models.CASCADE)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='Deposit')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    payment_date = models.DateTimeField(auto_now_add=True)
    reference = models.CharField(max_length=255, unique=True)
    qr_code_url = models.URLField(null=True, blank=True)
    description = models.TextField(null=True)

    def __str__(self):
        return f"{self.provider} - {self.amount} {self.wallet.currency}"
