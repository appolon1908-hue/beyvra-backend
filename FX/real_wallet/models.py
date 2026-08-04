import uuid

from django.conf import settings
from django.db import models

from integrations.models import Organization


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Asset(UUIDModel):
    symbol = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=120)
    decimals = models.PositiveSmallIntegerField()
    enabled = models.BooleanField(default=False)

    class Meta:
        db_table = "real_wallet_assets"


class Network(UUIDModel):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    enabled = models.BooleanField(default=False)

    class Meta:
        db_table = "real_wallet_networks"


class AssetNetwork(UUIDModel):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="networks")
    network = models.ForeignKey(Network, on_delete=models.PROTECT, related_name="assets")
    enabled = models.BooleanField(default=False)
    confirmations_required = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "real_wallet_asset_networks"
        constraints = [
            models.UniqueConstraint(fields=("asset", "network"), name="real_wallet_asset_network_unique")
        ]


class RealWallet(UUIDModel):
    tenant = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="real_wallets")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="real_wallets")
    status = models.CharField(max_length=24, default="ACTIVE")
    restricted_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "real_wallet_wallets"
        constraints = [
            models.UniqueConstraint(fields=("tenant", "owner"), name="real_wallet_owner_unique")
        ]


class AssetBalance(UUIDModel):
    wallet = models.ForeignKey(RealWallet, on_delete=models.PROTECT, related_name="balances")
    asset_network = models.ForeignKey(AssetNetwork, on_delete=models.PROTECT)
    posted_atomic = models.DecimalField(max_digits=78, decimal_places=0, default=0)
    pending_credit_atomic = models.DecimalField(max_digits=78, decimal_places=0, default=0)
    held_atomic = models.DecimalField(max_digits=78, decimal_places=0, default=0)
    reserved_atomic = models.DecimalField(max_digits=78, decimal_places=0, default=0)

    class Meta:
        db_table = "real_wallet_balances"
        constraints = [
            models.UniqueConstraint(fields=("wallet", "asset_network"), name="real_wallet_balance_unique"),
            models.CheckConstraint(condition=models.Q(posted_atomic__gte=0), name="real_wallet_posted_nonnegative"),
            models.CheckConstraint(condition=models.Q(pending_credit_atomic__gte=0), name="real_wallet_pending_nonnegative"),
            models.CheckConstraint(condition=models.Q(held_atomic__gte=0), name="real_wallet_held_nonnegative"),
            models.CheckConstraint(condition=models.Q(reserved_atomic__gte=0), name="real_wallet_reserved_nonnegative"),
        ]

    @property
    def available_atomic(self):
        return self.posted_atomic - self.held_atomic - self.reserved_atomic


class LedgerAccount(UUIDModel):
    tenant = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="real_ledger_accounts")
    owner_type = models.CharField(max_length=32)
    owner_id = models.UUIDField(null=True, blank=True)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    account_code = models.CharField(max_length=64)
    account_type = models.CharField(max_length=32)
    normal_side = models.CharField(max_length=6, choices=(("DEBIT", "Debit"), ("CREDIT", "Credit")))
    status = models.CharField(max_length=16, default="ACTIVE")

    class Meta:
        db_table = "real_ledger_accounts"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "owner_type", "owner_id", "asset", "account_code"),
                name="real_ledger_account_unique",
            )
        ]


class LedgerTransaction(UUIDModel):
    tenant = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="real_ledger_transactions")
    transaction_type = models.CharField(max_length=64)
    external_reference = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=255)
    status = models.CharField(max_length=16, default="PENDING")
    effective_at = models.DateTimeField()
    posted_at = models.DateTimeField(null=True, blank=True)
    correlation_id = models.UUIDField(null=True, blank=True)
    reversal_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "real_ledger_transactions"
        constraints = [
            models.UniqueConstraint(fields=("tenant", "idempotency_key"), name="real_ledger_idempotency_unique")
        ]


class LedgerEntry(UUIDModel):
    transaction = models.ForeignKey(LedgerTransaction, on_delete=models.PROTECT, related_name="entries")
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="entries")
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    direction = models.CharField(max_length=6, choices=(("DEBIT", "Debit"), ("CREDIT", "Credit")))
    amount_atomic = models.DecimalField(max_digits=78, decimal_places=0)

    class Meta:
        db_table = "real_ledger_entries"
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_atomic__gt=0), name="real_ledger_amount_positive")
        ]


class BalanceHold(UUIDModel):
    tenant = models.ForeignKey(Organization, on_delete=models.PROTECT)
    wallet = models.ForeignKey(RealWallet, on_delete=models.PROTECT, related_name="holds")
    asset_network = models.ForeignKey(AssetNetwork, on_delete=models.PROTECT)
    amount_atomic = models.DecimalField(max_digits=78, decimal_places=0)
    state = models.CharField(max_length=16, default="ACTIVE")
    reason = models.CharField(max_length=64)
    reference_id = models.UUIDField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "real_ledger_holds"
        constraints = [
            models.UniqueConstraint(fields=("tenant", "idempotency_key"), name="real_hold_idempotency_unique"),
            models.CheckConstraint(condition=models.Q(amount_atomic__gt=0), name="real_hold_amount_positive"),
        ]


class IdempotencyRecord(UUIDModel):
    tenant = models.ForeignKey(Organization, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    key = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    resource_type = models.CharField(max_length=64, blank=True)
    resource_id = models.UUIDField(null=True, blank=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "real_wallet_idempotency"
        constraints = [
            models.UniqueConstraint(fields=("tenant", "actor", "endpoint", "method", "key"), name="real_idempotency_scope_unique")
        ]


class OutboxEvent(UUIDModel):
    tenant = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.PROTECT)
    aggregate_type = models.CharField(max_length=64)
    aggregate_id = models.UUIDField()
    event_type = models.CharField(max_length=128)
    event_version = models.PositiveIntegerField(default=1)
    payload = models.JSONField(default=dict)
    correlation_id = models.UUIDField(null=True, blank=True)
    causation_id = models.UUIDField(null=True, blank=True)
    occurred_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "real_eventing_outbox"


class Deposit(UUIDModel):
    tenant = models.ForeignKey(Organization, on_delete=models.PROTECT)
    wallet = models.ForeignKey(RealWallet, on_delete=models.PROTECT, related_name="deposits")
    asset_network = models.ForeignKey(AssetNetwork, on_delete=models.PROTECT)
    transaction_hash = models.CharField(max_length=255)
    output_index = models.PositiveIntegerField(null=True, blank=True)
    amount_atomic = models.DecimalField(max_digits=78, decimal_places=0)
    state = models.CharField(max_length=32, default="DETECTED")
    confirmations = models.PositiveIntegerField(default=0)
    ledger_transaction = models.ForeignKey(LedgerTransaction, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        db_table = "real_wallet_deposits"
        constraints = [
            models.UniqueConstraint(fields=("asset_network", "transaction_hash", "output_index"), name="real_deposit_chain_event_unique")
        ]


class Withdrawal(UUIDModel):
    tenant = models.ForeignKey(Organization, on_delete=models.PROTECT)
    wallet = models.ForeignKey(RealWallet, on_delete=models.PROTECT, related_name="withdrawals")
    asset_network = models.ForeignKey(AssetNetwork, on_delete=models.PROTECT)
    destination = models.CharField(max_length=255)
    amount_atomic = models.DecimalField(max_digits=78, decimal_places=0)
    fee_atomic = models.DecimalField(max_digits=78, decimal_places=0, default=0)
    state = models.CharField(max_length=40, default="REQUESTED")
    hold = models.OneToOneField(BalanceHold, null=True, blank=True, on_delete=models.PROTECT)
    blockchain_transaction = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=255)

    class Meta:
        db_table = "real_wallet_withdrawals"
        constraints = [
            models.UniqueConstraint(fields=("tenant", "idempotency_key"), name="real_withdrawal_idempotency_unique"),
            models.CheckConstraint(condition=models.Q(amount_atomic__gt=0), name="real_withdrawal_amount_positive"),
        ]


class InternalTransfer(UUIDModel):
    tenant = models.ForeignKey(Organization, on_delete=models.PROTECT)
    source_wallet = models.ForeignKey(RealWallet, on_delete=models.PROTECT, related_name="outgoing_transfers")
    destination_wallet = models.ForeignKey(RealWallet, on_delete=models.PROTECT, related_name="incoming_transfers")
    asset_network = models.ForeignKey(AssetNetwork, on_delete=models.PROTECT)
    amount_atomic = models.DecimalField(max_digits=78, decimal_places=0)
    state = models.CharField(max_length=24, default="REQUESTED")
    idempotency_key = models.CharField(max_length=255)

    class Meta:
        db_table = "real_wallet_transfers"
        constraints = [
            models.UniqueConstraint(fields=("tenant", "idempotency_key"), name="real_transfer_idempotency_unique"),
            models.CheckConstraint(condition=models.Q(amount_atomic__gt=0), name="real_transfer_amount_positive"),
        ]


class FeatureFlag(models.Model):
    key = models.CharField(max_length=96, primary_key=True)
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "real_wallet_feature_flags"


class AuditEvent(UUIDModel):
    tenant = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    action = models.CharField(max_length=128)
    resource_type = models.CharField(max_length=64)
    resource_id = models.UUIDField(null=True, blank=True)
    request_id = models.CharField(max_length=128, blank=True)
    correlation_id = models.UUIDField(null=True, blank=True)
    outcome = models.CharField(max_length=32)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "real_wallet_audit_events"
