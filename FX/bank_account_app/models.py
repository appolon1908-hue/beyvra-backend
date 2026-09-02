from uuid import uuid4
from django.db.models import Sum
from django.db import models
from django.db.models import Q
from django.utils import timezone
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
    # Legacy plaintext is retained only for expand/contract migration. New
    # writes use the authenticated-encryption envelope and clear this field.
    account_number = models.CharField(max_length=50, null=True, blank=True)
    account_number_ciphertext = models.TextField(null=True, blank=True)
    account_number_nonce = models.CharField(max_length=64, null=True, blank=True)
    account_number_key_version = models.CharField(max_length=32, default="v1")
    account_number_fingerprint = models.CharField(max_length=32, default="", db_index=True)
    account_number_last_four = models.CharField(max_length=4, default="")
    is_active = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    account_holder_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255, null=True, blank=True,
                                 help_text='Last name of the account holder')
    routing_number = models.CharField(max_length=50, null=True, blank=True)
    routing_number_ciphertext = models.TextField(null=True, blank=True)
    routing_number_nonce = models.CharField(max_length=64, null=True, blank=True)
    routing_number_key_version = models.CharField(max_length=32, default="v1")
    routing_number_last_four = models.CharField(max_length=4, default="")
    swift_code = models.CharField(max_length=50, null=True, blank=True)
    swift_code_ciphertext = models.TextField(null=True, blank=True)
    swift_code_nonce = models.CharField(max_length=64, null=True, blank=True)
    swift_code_key_version = models.CharField(max_length=32, default="v1")
    swift_code_last_four = models.CharField(max_length=4, default="")
    iban = models.CharField(max_length=50, null=True, blank=True)
    iban_ciphertext = models.TextField(null=True, blank=True)
    iban_nonce = models.CharField(max_length=64, null=True, blank=True)
    iban_key_version = models.CharField(max_length=32, default="v1")
    iban_last_four = models.CharField(max_length=4, default="")
    country = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"BankAccount<{self.pk}> {self.bank_name} ****{self.account_number_last_four}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "account_number_fingerprint"),
                condition=~Q(account_number_fingerprint=""),
                name="unique_user_bank_account_fingerprint",
            )
        ]

    def retire(self):
        self.is_active = False
        self.revoked_at = timezone.now()
        self.save(update_fields=("is_active", "revoked_at", "updated_at"))


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
