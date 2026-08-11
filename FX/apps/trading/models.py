import uuid

from django.db import models

from apps.trading.domain.orders import OrderSide, OrderState, OrderType


class TradingOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    subject_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    instrument_id = models.CharField(max_length=64)
    order_type = models.CharField(max_length=16, choices=[(value.value, value.value) for value in OrderType])
    side = models.CharField(max_length=8, choices=[(value.value, value.value) for value in OrderSide])
    quantity = models.DecimalField(max_digits=36, decimal_places=18)
    limit_price = models.DecimalField(max_digits=36, decimal_places=18, null=True)
    stop_price = models.DecimalField(max_digits=36, decimal_places=18, null=True)
    filled_quantity = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    average_fill_price = models.DecimalField(max_digits=36, decimal_places=18, null=True)
    risk_decision_id = models.UUIDField(null=True)
    reservation_id = models.UUIDField(null=True)
    simulation = models.BooleanField(default=False)
    state = models.CharField(
        max_length=24,
        choices=[(value.value, value.value) for value in OrderState],
        default=OrderState.PENDING.value,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class RiskDecision(models.Model):
    class Decision(models.TextChoices):
        ALLOW = "ALLOW"
        DENY = "DENY"
        REVIEW = "REVIEW"

    decision_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    subject_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    order_id = models.UUIDField(null=True)
    decision = models.CharField(max_length=8, choices=Decision.choices)
    reason_codes = models.JSONField(default=list)
    policy_version = models.CharField(max_length=32)
    inputs_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)


class SimulatedAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    subject_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    status = models.CharField(max_length=16, default="ACTIVE")
    quote_currency = models.CharField(max_length=16, default="USD")
    total_balance = models.DecimalField(max_digits=36, decimal_places=18, default=10000)
    pending_balance = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("tenant_ref", "subject_ref", "account_ref"), name="simulation_account_scope_unique")]


class SimulatedReservation(models.Model):
    class State(models.TextChoices):
        ACTIVE = "ACTIVE"
        RELEASED = "RELEASED"
        CONSUMED = "CONSUMED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(SimulatedAccount, on_delete=models.PROTECT, related_name="reservations")
    order_id = models.UUIDField(unique=True)
    asset = models.CharField(max_length=32)
    original_amount = models.DecimalField(max_digits=36, decimal_places=18)
    remaining_amount = models.DecimalField(max_digits=36, decimal_places=18)
    state = models.CharField(max_length=16, choices=State.choices, default=State.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SimulatedTrade(models.Model):
    trade_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(TradingOrder, on_delete=models.PROTECT, related_name="simulated_trades")
    execution_id = models.CharField(max_length=128, unique=True)
    instrument_id = models.CharField(max_length=64)
    side = models.CharField(max_length=8)
    quantity = models.DecimalField(max_digits=36, decimal_places=18)
    price = models.DecimalField(max_digits=36, decimal_places=18)
    fee = models.DecimalField(max_digits=36, decimal_places=18)
    executed_at = models.DateTimeField()
    simulation = models.BooleanField(default=True)


class SimulatedPosition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(SimulatedAccount, on_delete=models.PROTECT, related_name="positions")
    instrument_id = models.CharField(max_length=64)
    quantity = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    average_price = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    realized_pnl = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("account", "instrument_id"), name="simulation_position_unique")]


class ReconciliationRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING"
        PASS = "PASS"
        FAIL = "FAIL"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.CharField(max_length=32)
    simulation = models.BooleanField(default=True)
    scope = models.CharField(max_length=32, default="full")
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    policy_version = models.CharField(max_length=32)
    candidate_sha = models.CharField(max_length=64)
    summary_hash = models.CharField(max_length=64, blank=True)
    check_count = models.PositiveIntegerField(default=0)
    violation_count = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(status=ReconciliationRun.Status.RUNNING).exists():
            raise ValueError("RECONCILIATION_RUN_IMMUTABLE")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("RECONCILIATION_RUN_IMMUTABLE")


class ReconciliationViolation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ReconciliationRun, on_delete=models.PROTECT, related_name="violations")
    check_code = models.CharField(max_length=64)
    severity = models.CharField(max_length=16)
    entity_type = models.CharField(max_length=32)
    opaque_entity_ref = models.CharField(max_length=64)
    evidence_hash = models.CharField(max_length=64)
    detected_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("RECONCILIATION_VIOLATION_IMMUTABLE")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("RECONCILIATION_VIOLATION_IMMUTABLE")


class ExecutionProviderRecord(models.Model):
    class Mode(models.TextChoices):
        SIMULATION = "SIMULATION"
        PAPER = "PAPER"
        LIVE = "LIVE"
    class Health(models.TextChoices):
        HEALTHY = "HEALTHY"
        DEGRADED = "DEGRADED"
        UNAVAILABLE = "UNAVAILABLE"
        HALTED = "HALTED"

    provider_id = models.CharField(max_length=64, primary_key=True)
    display_name = models.CharField(max_length=128)
    mode = models.CharField(max_length=16, choices=Mode.choices)
    enabled = models.BooleanField(default=False)
    health = models.CharField(max_length=16, choices=Health.choices, default=Health.HALTED)
    capabilities = models.JSONField(default=dict)
    supported_asset_classes = models.JSONField(default=list)
    supported_order_types = models.JSONField(default=list)
    supported_venues = models.JSONField(default=list)
    circuit_open_until = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class ExecutionVenue(models.Model):
    venue_id = models.CharField(max_length=64, primary_key=True)
    display_name = models.CharField(max_length=128)
    asset_classes = models.JSONField(default=list)
    order_types = models.JSONField(default=list)
    active = models.BooleanField(default=False)
    delayed = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)


class ExecutionRoutingDecision(models.Model):
    class Status(models.TextChoices):
        SELECTED = "SELECTED"
        DENIED = "DENIED"
        UNKNOWN = "UNKNOWN"

    decision_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(TradingOrder, on_delete=models.PROTECT, related_name="routing_decisions", null=True)
    tenant_ref = models.CharField(max_length=128)
    subject_ref = models.CharField(max_length=128)
    mode = models.CharField(max_length=16)
    status = models.CharField(max_length=16, choices=Status.choices)
    selected_provider_id = models.CharField(max_length=64, blank=True)
    selected_venue_id = models.CharField(max_length=64, blank=True)
    policy_version = models.CharField(max_length=32)
    candidate_evidence = models.JSONField(default=list)
    exclusion_reasons = models.JSONField(default=list)
    market_snapshot_hash = models.CharField(max_length=64)
    request_hash = models.CharField(max_length=64)
    reference_price = models.DecimalField(max_digits=36, decimal_places=18)
    created_at = models.DateTimeField(auto_now_add=True)

    def delete(self, *args, **kwargs):
        raise ValueError("ROUTING_DECISION_IMMUTABLE")


class ExecutionQualityReport(models.Model):
    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(TradingOrder, on_delete=models.PROTECT, related_name="execution_quality")
    routing_decision = models.ForeignKey(ExecutionRoutingDecision, on_delete=models.PROTECT)
    reference_price = models.DecimalField(max_digits=36, decimal_places=18)
    execution_price = models.DecimalField(max_digits=36, decimal_places=18)
    filled_quantity = models.DecimalField(max_digits=36, decimal_places=18)
    slippage_bps = models.DecimalField(max_digits=24, decimal_places=8)
    price_improvement_amount = models.DecimalField(max_digits=36, decimal_places=18)
    price_improvement_bps = models.DecimalField(max_digits=24, decimal_places=8)
    measurement_version = models.CharField(max_length=32)
    evidence_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def delete(self, *args, **kwargs):
        raise ValueError("EXECUTION_QUALITY_IMMUTABLE")
