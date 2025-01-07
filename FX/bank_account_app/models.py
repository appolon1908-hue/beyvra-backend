from uuid import uuid4
from django.db.models import Sum
from django.db import models
from users.models import User
from wallet.models import Wallet, Currency


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BankAccount(TimeStampedModel):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50, unique=True)
    account_holder_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255, null=True, blank=True,
                                 help_text='Last name of the account holder')
    routing_number = models.CharField(max_length=50, null=True, blank=True)
    swift_code = models.CharField(max_length=50, null=True, blank=True)
    iban = models.CharField(max_length=50, null=True, blank=True)
    country = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"{self.user.email} - {self.bank_name} - {self.account_number}"


class WithdrawalRequest(TimeStampedModel):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled'),
    ]
    withdrawal_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawal_requests')
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE,
                               related_name='withdrawal_requests', null=True, blank=True)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE,
                                     related_name='withdrawal_requests', null=True, blank=True)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_withdrawals')
    request_date = models.DateTimeField(auto_now_add=True)
    approval_date = models.DateTimeField(null=True, blank=True)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    description = models.TextField(null=True, blank=True)
    network_fee = models.DecimalField(
        max_digits=20, decimal_places=2, default=0)
    txid = models.CharField(max_length=255, null=True,
                            blank=True, help_text='Transaction reference ID')
    estimated_completion_time = models.DateTimeField(null=True, blank=True)
    # In case withdrawal gets rejected/cancelled
    reason = models.TextField(null=True, blank=True)
    denial_date = models.DateTimeField(null=True, blank=True)
    # Sender details
    sender_name = models.CharField(max_length=50, null=True, blank=True)
    sender_account_number = models.CharField(max_length=50, null=True, blank=True)
    sender_contact_info = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"Withdrawal Request - {self.user.email} - {self.amount} - {self.status}"

    @property
    def total_withdrawal_amount(self):
        return WithdrawalRequest.objects.filter(
            user=self.user, status='Approved').aggregate(Sum('amount'))

    @property
    def total_withdrawal_requests(self):
        return WithdrawalRequest.objects.filter(user=self.user).count()

    @property
    def total_pending_requests(self):
        return WithdrawalRequest.objects.filter(user=self.user, status='Pending').count()

    @property
    def total_approved_requests(self):
        return WithdrawalRequest.objects.filter(user=self.user, status='Approved').count()

    @property
    def total_rejected_requests(self):
        return WithdrawalRequest.objects.filter(user=self.user, status='Rejected').count()

    @property
    def total_cancelled_requests(self):
        return WithdrawalRequest.objects.filter(user=self.user, status='Cancelled').count()
