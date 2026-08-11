import uuid

from django.db import models


class ImmutableModel(models.Model):
    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ValueError("POST_TRADE_EVIDENCE_APPEND_ONLY")


class Trade(ImmutableModel):
    STATES = ("CAPTURED", "VALIDATING", "VALIDATED", "ALLOCATION_PENDING", "ALLOCATED", "SETTLEMENT_PENDING", "SETTLEMENT_INSTRUCTED", "SETTLEMENT_PROCESSING", "SETTLED", "EXCEPTION", "FAILED", "REVERSED", "CANCELLED")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    order_id = models.UUIDField()
    execution_id = models.CharField(max_length=128, unique=True)
    instrument_id = models.CharField(max_length=64)
    side = models.CharField(max_length=8)
    quantity = models.DecimalField(max_digits=36, decimal_places=18)
    price = models.DecimalField(max_digits=36, decimal_places=18)
    gross_notional = models.DecimalField(max_digits=36, decimal_places=18)
    trade_currency = models.CharField(max_length=16)
    execution_provider_id = models.CharField(max_length=64)
    venue_id = models.CharField(max_length=64)
    execution_mode = models.CharField(max_length=24)
    trade_time = models.DateTimeField()
    captured_at = models.DateTimeField()
    settlement_date = models.DateField()
    trade_state = models.CharField(max_length=32, choices=[(v, v) for v in STATES], default="CAPTURED")
    routing_decision_id = models.UUIDField(null=True, blank=True)
    source_event_id = models.UUIDField(unique=True)
    version = models.PositiveIntegerField(default=1)
    simulation = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=("tenant_ref", "account_ref", "trade_time"), name="post_trade_account_idx"), models.Index(fields=("instrument_id", "trade_time"), name="post_trade_instr_idx")]

    def save(self, *args, **kwargs):
        update_fields = set(kwargs.get("update_fields") or ())
        if self.pk and update_fields and not update_fields.issubset({"trade_state", "version", "updated_at"}):
            raise ValueError("DESTRUCTIVE_TRADE_EDIT")
        if self.pk and not update_fields:
            previous = type(self).objects.filter(pk=self.pk).values("tenant_ref", "account_ref", "order_id", "execution_id", "instrument_id", "side", "quantity", "price", "gross_notional", "trade_currency", "execution_provider_id", "venue_id", "execution_mode", "trade_time", "captured_at", "settlement_date", "routing_decision_id", "source_event_id", "simulation").first()
            if previous and any(getattr(self, field) != value for field, value in previous.items()):
                raise ValueError("DESTRUCTIVE_TRADE_EDIT")
        return super().save(*args, **kwargs)


class FeeSnapshot(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.OneToOneField(Trade, on_delete=models.PROTECT, related_name="fee_snapshot")
    commission = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    exchange_fee = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    broker_fee = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    regulatory_fee = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    other_fee = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    total_fee = models.DecimalField(max_digits=36, decimal_places=18)
    currency = models.CharField(max_length=16)
    pricing_policy_version = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)


class TradeAllocation(models.Model):
    METHODS = ("DIRECT_ACCOUNT", "SUBACCOUNT", "STRATEGY", "MANUAL_REVIEW", "INSTITUTIONAL_FUTURE")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.ForeignKey(Trade, on_delete=models.PROTECT, related_name="allocations")
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    subaccount_ref = models.CharField(max_length=128, blank=True)
    strategy_ref = models.CharField(max_length=128, blank=True)
    allocation_quantity = models.DecimalField(max_digits=36, decimal_places=18)
    allocation_notional = models.DecimalField(max_digits=36, decimal_places=18)
    allocation_method = models.CharField(max_length=32, choices=[(v, v) for v in METHODS])
    status = models.CharField(max_length=24, default="ALLOCATED")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("trade", "account_ref", "subaccount_ref", "strategy_ref"), name="post_trade_allocation_unique")]


class SettlementObligation(ImmutableModel):
    TYPES = ("CASH_DEBIT", "CASH_CREDIT", "ASSET_DELIVERY", "ASSET_RECEIPT", "FEE_DEBIT", "REBATE_CREDIT")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.ForeignKey(Trade, on_delete=models.PROTECT, related_name="obligations")
    account_ref = models.CharField(max_length=128)
    obligation_type = models.CharField(max_length=24, choices=[(v, v) for v in TYPES])
    asset = models.CharField(max_length=32)
    quantity = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    currency = models.CharField(max_length=16)
    amount = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    direction = models.CharField(max_length=8, choices=(("DEBIT", "DEBIT"), ("CREDIT", "CREDIT")))
    due_date = models.DateField()
    state = models.CharField(max_length=24, default="PENDING")
    calculation_policy_version = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("trade", "obligation_type"), name="post_trade_obligation_unique")]


class SettlementInstruction(models.Model):
    TYPES = ("DELIVERY_VERSUS_PAYMENT", "FREE_OF_PAYMENT", "CASH_SETTLEMENT", "ASSET_SETTLEMENT", "INTERNAL_SIMULATION")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.OneToOneField(Trade, on_delete=models.PROTECT, related_name="settlement_instruction")
    account_ref = models.CharField(max_length=128)
    instrument_id = models.CharField(max_length=64)
    settlement_type = models.CharField(max_length=32, choices=[(v, v) for v in TYPES])
    settlement_date = models.DateField()
    deliver_asset = models.CharField(max_length=32)
    deliver_quantity = models.DecimalField(max_digits=36, decimal_places=18)
    receive_asset = models.CharField(max_length=32)
    receive_quantity = models.DecimalField(max_digits=36, decimal_places=18)
    currency = models.CharField(max_length=16)
    cash_amount = models.DecimalField(max_digits=36, decimal_places=18)
    fee_amount = models.DecimalField(max_digits=36, decimal_places=18)
    state = models.CharField(max_length=32, default="SETTLEMENT_PENDING")
    idempotency_key = models.CharField(max_length=128, unique=True)
    policy_version = models.CharField(max_length=32)
    simulation = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TradePositionEffect(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.ForeignKey(Trade, on_delete=models.PROTECT, related_name="position_effects")
    account_ref = models.CharField(max_length=128)
    instrument_id = models.CharField(max_length=64)
    quantity_delta = models.DecimalField(max_digits=36, decimal_places=18)
    cost_basis_delta = models.DecimalField(max_digits=36, decimal_places=18, null=True)
    effect_type = models.CharField(max_length=32, default="TRADE")
    applied_at = models.DateTimeField()
    version = models.PositiveIntegerField(default=1)
    simulation = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("trade", "effect_type"), name="post_trade_position_effect_unique")]


class TradeConfirmation(ImmutableModel):
    STATES = ("GENERATED", "CORRECTED", "SUPERSEDED", "REVERSED")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.ForeignKey(Trade, on_delete=models.PROTECT, related_name="confirmations")
    account_ref = models.CharField(max_length=128)
    confirmation_number = models.CharField(max_length=64, unique=True)
    version = models.PositiveIntegerField(default=1)
    trade_date = models.DateField()
    settlement_date = models.DateField()
    instrument_snapshot = models.JSONField(default=dict)
    side = models.CharField(max_length=8)
    quantity = models.DecimalField(max_digits=36, decimal_places=18)
    price = models.DecimalField(max_digits=36, decimal_places=18)
    gross_notional = models.DecimalField(max_digits=36, decimal_places=18)
    fees = models.DecimalField(max_digits=36, decimal_places=18)
    net_amount = models.DecimalField(max_digits=36, decimal_places=18)
    currency = models.CharField(max_length=16)
    venue_safe = models.CharField(max_length=64)
    execution_mode = models.CharField(max_length=24)
    generated_at = models.DateTimeField()
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, choices=[(v, v) for v in STATES], default="GENERATED")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("trade", "version"), name="post_trade_confirmation_version_unique")]


class SettlementCalendar(models.Model):
    CONVENTIONS = ("T_PLUS_0", "T_PLUS_1", "T_PLUS_2", "INSTANT", "BLOCKCHAIN_FINALITY", "CUSTOM")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64)
    asset_class = models.CharField(max_length=32)
    venue_id = models.CharField(max_length=64, blank=True)
    currency = models.CharField(max_length=16, blank=True)
    settlement_convention = models.CharField(max_length=32, choices=[(v, v) for v in CONVENTIONS])
    timezone = models.CharField(max_length=64, default="UTC")
    calendar_ref = models.CharField(max_length=64)
    holidays = models.JSONField(default=list)
    policy_version = models.CharField(max_length=32)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("code", "policy_version"), name="post_trade_calendar_version_unique")]


class PostTradeException(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    trade = models.ForeignKey(Trade, null=True, blank=True, on_delete=models.PROTECT)
    settlement_instruction = models.ForeignKey(SettlementInstruction, null=True, blank=True, on_delete=models.PROTECT)
    exception_type = models.CharField(max_length=64)
    severity = models.CharField(max_length=16)
    state = models.CharField(max_length=16, default="OPEN")
    detected_at = models.DateTimeField()
    assigned_to = models.CharField(max_length=128, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_code = models.CharField(max_length=64, blank=True)
    requested_by = models.CharField(max_length=128, blank=True)
    approved_by = models.CharField(max_length=128, blank=True)
    evidence_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("trade", "exception_type"), condition=models.Q(trade__isnull=False, state__in=("OPEN", "ASSIGNED", "INVESTIGATING", "ESCALATED")), name="post_trade_open_exception_unique")]


class TradeCorrection(models.Model):
    TYPES = ("REVERSAL", "CORRECTION", "CANCEL_AND_REBOOK")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_trade = models.ForeignKey(Trade, on_delete=models.PROTECT, related_name="corrections")
    correction_type = models.CharField(max_length=24, choices=[(v, v) for v in TYPES])
    replacement_trade = models.ForeignKey(Trade, null=True, blank=True, on_delete=models.PROTECT, related_name="replacement_for")
    reason_code = models.CharField(max_length=64)
    requested_by = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=16, default="PENDING")


class PostTradeAudit(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    actor_ref = models.CharField(max_length=128)
    action = models.CharField(max_length=128)
    resource_type = models.CharField(max_length=64)
    resource_ref = models.CharField(max_length=128)
    evidence_hash = models.CharField(max_length=64)
    reason = models.CharField(max_length=255)
    occurred_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=("tenant_ref", "resource_type", "resource_ref", "occurred_at"), name="post_trade_audit_idx")]


class PostTradeReconciliationRun(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField()
    status = models.CharField(max_length=16)
    checks = models.JSONField(default=dict)
    violations = models.JSONField(default=list)
    candidate_sha = models.CharField(max_length=64)
    policy_version = models.CharField(max_length=32)
