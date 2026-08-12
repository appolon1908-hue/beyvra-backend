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
    state = models.CharField(
        max_length=24,
        choices=[(value.value, value.value) for value in OrderState],
        default=OrderState.PENDING.value,
    )
    simulation = models.BooleanField(default=True, editable=False)
    eligibility_policy_version = models.CharField(max_length=32, default="")
    eligibility_result = models.CharField(max_length=20, default="DENIED")
    eligibility_reason_codes = models.JSONField(default=list)
    eligibility_evaluated_at = models.DateTimeField(null=True)
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("tenant_ref", "subject_ref", "idempotency_key"), condition=~models.Q(idempotency_key=""), name="unique_sim_order_idempotency")]


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
    provider_type = models.CharField(max_length=16, default="SIMULATION")
    environment = models.CharField(max_length=16, default="SIMULATION")
    priority = models.PositiveIntegerField(default=100)
    governance_state = models.CharField(max_length=40, default="DISCOVERED")
    paper_supported = models.BooleanField(default=False)
    live_supported = models.BooleanField(default=False)
    fix_supported = models.BooleanField(default=False)
    api_supported = models.BooleanField(default=False)
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
    venue_type = models.CharField(max_length=32, default="INTERNAL")
    timezone = models.CharField(max_length=64, default="UTC")
    status = models.CharField(max_length=16, default="DISABLED")
    routing_enabled = models.BooleanField(default=False)
    paper_supported = models.BooleanField(default=False)
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
    evidence_hash = models.CharField(max_length=64, blank=True)
    pricing_snapshot_hash = models.CharField(max_length=64, blank=True)
    risk_snapshot_hash = models.CharField(max_length=64, blank=True)
    selected_score = models.DecimalField(max_digits=24, decimal_places=8, null=True)
    reference_price = models.DecimalField(max_digits=36, decimal_places=18)
    revision = models.PositiveIntegerField(default=1)
    supersedes = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="revisions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("order", "revision"), condition=models.Q(order__isnull=False), name="execution_route_order_revision_unique")]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("ROUTING_DECISION_IMMUTABLE")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("ROUTING_DECISION_IMMUTABLE")


class ExecutionQualityReport(models.Model):
    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(TradingOrder, on_delete=models.PROTECT, related_name="execution_quality_reports")
    routing_decision = models.ForeignKey(ExecutionRoutingDecision, on_delete=models.PROTECT)
    reference_price = models.DecimalField(max_digits=36, decimal_places=18)
    execution_price = models.DecimalField(max_digits=36, decimal_places=18)
    filled_quantity = models.DecimalField(max_digits=36, decimal_places=18)
    slippage_bps = models.DecimalField(max_digits=24, decimal_places=8)
    price_improvement_amount = models.DecimalField(max_digits=36, decimal_places=18)
    price_improvement_bps = models.DecimalField(max_digits=24, decimal_places=8)
    measurement_version = models.CharField(max_length=32)
    evidence_hash = models.CharField(max_length=64)
    arrival_price = models.DecimalField(max_digits=36, decimal_places=18, null=True)
    decision_price = models.DecimalField(max_digits=36, decimal_places=18, null=True)
    fees = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    fill_rate = models.DecimalField(max_digits=12, decimal_places=8, default=0)
    unfilled_quantity = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    quality_state = models.CharField(max_length=32, default="MEASURED")
    time_to_first_fill_ms = models.PositiveIntegerField(null=True)
    time_to_complete_ms = models.PositiveIntegerField(null=True)
    revision = models.PositiveIntegerField(default=1)
    supersedes = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="revisions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("order", "revision"), name="execution_quality_order_revision_unique")]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("EXECUTION_QUALITY_IMMUTABLE")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("EXECUTION_QUALITY_IMMUTABLE")


class ExecutionProviderCapability(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(ExecutionProviderRecord, on_delete=models.PROTECT, related_name="capability_records")
    asset_class = models.CharField(max_length=16)
    venue = models.ForeignKey(ExecutionVenue, on_delete=models.PROTECT, null=True, blank=True)
    capability_type = models.CharField(max_length=32)
    enabled = models.BooleanField(default=False)
    source = models.CharField(max_length=32)
    source_version = models.CharField(max_length=64)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField()
    metadata_safe = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("provider", "asset_class", "venue", "capability_type", "source_version"), name="execution_provider_capability_unique")]


class VenueCapability(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venue = models.ForeignKey(ExecutionVenue, on_delete=models.PROTECT, related_name="capability_records")
    asset_class = models.CharField(max_length=16)
    order_type = models.CharField(max_length=16)
    time_in_force = models.CharField(max_length=8)
    session_type = models.CharField(max_length=16, default="REGULAR")
    short_sell_supported = models.BooleanField(default=False)
    fractional_supported = models.BooleanField(default=False)
    minimum_quantity = models.DecimalField(max_digits=36, decimal_places=18)
    quantity_increment = models.DecimalField(max_digits=36, decimal_places=18)
    price_increment = models.DecimalField(max_digits=36, decimal_places=18)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    source_version = models.CharField(max_length=64)


class BestExecutionPolicy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64)
    asset_class = models.CharField(max_length=16)
    account_type = models.CharField(max_length=32, blank=True)
    instrument_id = models.CharField(max_length=64, blank=True)
    mode = models.CharField(max_length=16)
    price_weight = models.DecimalField(max_digits=8, decimal_places=6)
    fee_weight = models.DecimalField(max_digits=8, decimal_places=6)
    latency_weight = models.DecimalField(max_digits=8, decimal_places=6)
    fill_probability_weight = models.DecimalField(max_digits=8, decimal_places=6)
    liquidity_weight = models.DecimalField(max_digits=8, decimal_places=6)
    reliability_weight = models.DecimalField(max_digits=8, decimal_places=6)
    market_impact_weight = models.DecimalField(max_digits=8, decimal_places=6)
    status = models.CharField(max_length=16, default="DRAFT")
    policy_version = models.CharField(max_length=32)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("code", "policy_version"), name="best_execution_policy_version_unique")]


class ExecutionRouteCandidate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    decision = models.ForeignKey(ExecutionRoutingDecision, on_delete=models.PROTECT, related_name="candidates")
    provider = models.ForeignKey(ExecutionProviderRecord, on_delete=models.PROTECT)
    venue = models.ForeignKey(ExecutionVenue, on_delete=models.PROTECT)
    mode = models.CharField(max_length=16)
    expected_price = models.DecimalField(max_digits=36, decimal_places=18)
    expected_fee = models.DecimalField(max_digits=36, decimal_places=18)
    expected_slippage = models.DecimalField(max_digits=36, decimal_places=18)
    available_quantity = models.DecimalField(max_digits=36, decimal_places=18)
    estimated_fill_probability = models.DecimalField(max_digits=8, decimal_places=6)
    estimated_latency_ms = models.PositiveIntegerField()
    provider_health = models.CharField(max_length=16)
    score = models.DecimalField(max_digits=24, decimal_places=8)
    eligible = models.BooleanField()
    rejection_reasons = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("ROUTE_CANDIDATE_IMMUTABLE")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("ROUTE_CANDIDATE_IMMUTABLE")


class CanonicalExecution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(TradingOrder, on_delete=models.PROTECT, related_name="canonical_executions")
    provider = models.ForeignKey(ExecutionProviderRecord, on_delete=models.PROTECT)
    venue = models.ForeignKey(ExecutionVenue, on_delete=models.PROTECT)
    provider_order_ref_hash = models.CharField(max_length=64, blank=True)
    provider_execution_ref_hash = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=24, default="CREATED")
    quantity = models.DecimalField(max_digits=36, decimal_places=18)
    filled_quantity = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    remaining_quantity = models.DecimalField(max_digits=36, decimal_places=18)
    average_price = models.DecimalField(max_digits=36, decimal_places=18, null=True)
    last_fill_price = models.DecimalField(max_digits=36, decimal_places=18, null=True)
    last_fill_quantity = models.DecimalField(max_digits=36, decimal_places=18, null=True)
    submitted_at = models.DateTimeField(null=True)
    accepted_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    provider_timestamp = models.DateTimeField(null=True)
    received_at = models.DateTimeField(auto_now_add=True)
    mode = models.CharField(max_length=16)
    version = models.PositiveIntegerField(default=1)


class ExecutionProviderHealth(models.Model):
    provider = models.OneToOneField(ExecutionProviderRecord, on_delete=models.PROTECT, primary_key=True, related_name="health_record")
    state = models.CharField(max_length=16, default="UNKNOWN")
    circuit_state = models.CharField(max_length=16, default="CLOSED")
    last_success_at = models.DateTimeField(null=True)
    last_failure_at = models.DateTimeField(null=True)
    latency_p50_ms = models.PositiveIntegerField(default=0)
    latency_p95_ms = models.PositiveIntegerField(default=0)
    error_rate = models.DecimalField(max_digits=8, decimal_places=6, default=0)
    reject_rate = models.DecimalField(max_digits=8, decimal_places=6, default=0)
    connection_state = models.CharField(max_length=16, default="DISCONNECTED")
    last_checked_at = models.DateTimeField(auto_now=True)


class UnknownExecutionOutcome(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.OneToOneField(CanonicalExecution, on_delete=models.PROTECT, related_name="unknown_outcome")
    classification = models.CharField(max_length=32, default="AMBIGUOUS_SUBMISSION")
    state = models.CharField(max_length=16, default="UNRESOLVED")
    lookup_attempts = models.PositiveIntegerField(default=0)
    last_lookup_at = models.DateTimeField(null=True)
    resolution_evidence_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True)


class ExecutionReconciliationRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16)
    candidate_sha = models.CharField(max_length=64)
    check_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    critical_count = models.PositiveIntegerField(default=0)
    evidence_hash = models.CharField(max_length=64)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField()

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("EXECUTION_RECONCILIATION_IMMUTABLE")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("EXECUTION_RECONCILIATION_IMMUTABLE")


class ExecutionGovernanceChange(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        APPROVED = "APPROVED"
        REJECTED = "REJECTED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(ExecutionProviderRecord, on_delete=models.PROTECT, related_name="governance_changes")
    action = models.CharField(max_length=32)
    requested_by_ref = models.CharField(max_length=128)
    reviewed_by_ref = models.CharField(max_length=128, blank=True)
    reason = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("provider", "action"), condition=models.Q(status="PENDING"), name="one_pending_execution_governance_change")]
