import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class SimulationModel(models.Model):
    simulation = models.BooleanField(default=True, editable=False)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if not self.simulation:
            raise ValidationError("TREASURY_SIMULATION_REQUIRED")


class TreasuryAccount(SimulationModel):
    ENVIRONMENTS = (("SIMULATION", "Simulation"), ("PAPER", "Paper"), ("SANDBOX_REFERENCE", "Sandbox reference"))
    TYPES = tuple((v, v) for v in ("SIMULATION_CASH", "BROKER_CASH_REFERENCE", "CUSTODY_REFERENCE", "CLEARING_REFERENCE", "SETTLEMENT_REFERENCE", "OMNIBUS_REFERENCE", "SEGREGATED_REFERENCE", "HOUSE_REFERENCE", "COLLATERAL_REFERENCE"))
    SEGREGATION = tuple((v, v) for v in ("CLIENT_SEGREGATED", "OMNIBUS_CLIENT", "HOUSE", "CLEARING", "CUSTODY", "UNKNOWN"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("integrations.Organization", on_delete=models.PROTECT, related_name="treasury_accounts")
    institution_id = models.UUIDField(null=True, blank=True)
    subaccount_id = models.UUIDField(null=True, blank=True)
    account_type = models.CharField(max_length=40, choices=TYPES)
    provider_id = models.CharField(max_length=80, blank=True)
    external_account_ref = models.CharField(max_length=160, blank=True)
    currency = models.CharField(max_length=12, blank=True)
    asset = models.CharField(max_length=32, blank=True)
    environment = models.CharField(max_length=24, choices=ENVIRONMENTS, default="SIMULATION")
    status = models.CharField(max_length=24, default="ACTIVE")
    segregation_class = models.CharField(max_length=24, choices=SEGREGATION, default="UNKNOWN")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gt=models.F("effective_from")), name="treasury_account_valid_dates")]


class TreasuryCashPosition(SimulationModel):
    SOURCES = tuple((v, v) for v in ("SIMULATION_LEDGER", "FINANCIAL_SERVICE_FIXTURE", "BROKER_PAPER_FIXTURE", "CUSTODY_SANDBOX_FIXTURE", "RECONCILIATION_IMPORT"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    treasury_account = models.ForeignKey(TreasuryAccount, on_delete=models.PROTECT, related_name="cash_positions")
    currency = models.CharField(max_length=12)
    gross_amount = models.DecimalField(max_digits=30, decimal_places=10)
    reserved_amount = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    available_amount = models.DecimalField(max_digits=30, decimal_places=10)
    encumbered_amount = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    unencumbered_amount = models.DecimalField(max_digits=30, decimal_places=10)
    source = models.CharField(max_length=40, choices=SOURCES)
    as_of = models.DateTimeField()

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(gross_amount__gte=0, reserved_amount__gte=0, available_amount__gte=0, encumbered_amount__gte=0, unencumbered_amount__gte=0), name="treasury_cash_nonnegative")]


class LiquiditySnapshot(SimulationModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("integrations.Organization", on_delete=models.PROTECT)
    institution_id = models.UUIDField()
    currency = models.CharField(max_length=12)
    gross_cash = models.DecimalField(max_digits=30, decimal_places=10)
    available_cash = models.DecimalField(max_digits=30, decimal_places=10)
    encumbered_cash = models.DecimalField(max_digits=30, decimal_places=10)
    settlement_due = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    margin_due = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    withdrawal_due_simulation = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    expected_inflows = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    expected_outflows = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    net_available_liquidity = models.DecimalField(max_digits=30, decimal_places=10)
    liquidity_buffer = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    liquidity_surplus_deficit = models.DecimalField(max_digits=30, decimal_places=10)
    as_of = models.DateTimeField()
    policy_version = models.CharField(max_length=64)


class LiquidityBufferPolicy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("integrations.Organization", on_delete=models.PROTECT)
    scope_type = models.CharField(max_length=24)
    scope_ref = models.CharField(max_length=128, blank=True)
    currency = models.CharField(max_length=12)
    buffer_type = models.CharField(max_length=40)
    buffer_value = models.DecimalField(max_digits=30, decimal_places=10)
    status = models.CharField(max_length=24, default="SIMULATION")
    policy_version = models.CharField(max_length=64)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)


class FundingRequirement(SimulationModel):
    TYPES = tuple((v, v) for v in ("SETTLEMENT", "MARGIN", "COLLATERAL", "WITHDRAWAL_SIMULATION", "FEE", "CUSTODY", "BROKER", "CLEARING", "LIQUIDITY_BUFFER", "OTHER"))
    STATES = tuple((v, v) for v in ("FORECAST", "CONFIRMED_SIMULATION", "FUNDED_SIMULATION", "SHORTFALL", "CANCELLED", "EXCEPTION"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("integrations.Organization", on_delete=models.PROTECT)
    institution_id = models.UUIDField()
    subaccount_id = models.UUIDField(null=True, blank=True)
    treasury_account = models.ForeignKey(TreasuryAccount, null=True, blank=True, on_delete=models.PROTECT)
    requirement_type = models.CharField(max_length=32, choices=TYPES)
    currency_or_asset = models.CharField(max_length=32)
    amount_or_quantity = models.DecimalField(max_digits=30, decimal_places=10)
    due_at = models.DateTimeField()
    priority = models.CharField(max_length=32)
    source_ref = models.CharField(max_length=128)
    state = models.CharField(max_length=32, choices=STATES, default="FORECAST")
    policy_version = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount_or_quantity__gt=0), name="funding_requirement_positive"), models.UniqueConstraint(fields=("tenant", "source_ref", "requirement_type"), name="funding_requirement_source_unique")]


class IntradayFundingWindow(SimulationModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("integrations.Organization", on_delete=models.PROTECT)
    institution_id = models.UUIDField()
    currency = models.CharField(max_length=12)
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    opening_liquidity = models.DecimalField(max_digits=30, decimal_places=10)
    expected_inflows = models.DecimalField(max_digits=30, decimal_places=10)
    expected_outflows = models.DecimalField(max_digits=30, decimal_places=10)
    peak_funding_need = models.DecimalField(max_digits=30, decimal_places=10)
    minimum_liquidity = models.DecimalField(max_digits=30, decimal_places=10)
    closing_liquidity = models.DecimalField(max_digits=30, decimal_places=10)


class TreasuryCollateralPosition(SimulationModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    treasury_account = models.ForeignKey(TreasuryAccount, on_delete=models.PROTECT, related_name="collateral_positions")
    instrument_id_or_asset = models.CharField(max_length=128)
    quantity = models.DecimalField(max_digits=30, decimal_places=10)
    reference_price = models.DecimalField(max_digits=30, decimal_places=10)
    gross_value = models.DecimalField(max_digits=30, decimal_places=10)
    haircut_rate = models.DecimalField(max_digits=12, decimal_places=10)
    eligible_value = models.DecimalField(max_digits=30, decimal_places=10)
    encumbered_quantity = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    free_quantity = models.DecimalField(max_digits=30, decimal_places=10)
    currency = models.CharField(max_length=12)
    quality_state = models.CharField(max_length=24)
    as_of = models.DateTimeField()

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gte=0, encumbered_quantity__gte=0, free_quantity__gte=0), name="treasury_collateral_nonnegative")]


class CollateralMobilityPolicy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("integrations.Organization", on_delete=models.PROTECT)
    from_account_type = models.CharField(max_length=40)
    to_account_type = models.CharField(max_length=40)
    asset_class = models.CharField(max_length=32)
    asset = models.CharField(max_length=64, blank=True)
    movement_type = models.CharField(max_length=40)
    allowed = models.BooleanField(default=False)
    minimum_buffer = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    settlement_delay = models.DurationField(default=0)
    policy_version = models.CharField(max_length=64)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)


class AssetEncumbrance(SimulationModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    treasury_account = models.ForeignKey(TreasuryAccount, on_delete=models.PROTECT, related_name="encumbrances")
    asset = models.CharField(max_length=64)
    quantity_or_amount = models.DecimalField(max_digits=30, decimal_places=10)
    encumbrance_type = models.CharField(max_length=32)
    source_ref = models.CharField(max_length=128)
    priority = models.PositiveSmallIntegerField(default=0)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=24, default="ACTIVE")


class TreasuryTransferPlan(SimulationModel):
    STATES = tuple((v, v) for v in ("PROPOSED", "VALIDATED", "APPROVED_SIMULATION", "SIMULATED", "REJECTED", "CANCELLED"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("integrations.Organization", on_delete=models.PROTECT)
    institution_id = models.UUIDField()
    plan_type = models.CharField(max_length=32)
    state = models.CharField(max_length=24, choices=STATES, default="PROPOSED")
    currency_or_asset = models.CharField(max_length=32)
    required_amount_or_quantity = models.DecimalField(max_digits=30, decimal_places=10)
    policy_version = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("tenant", "idempotency_key"), name="treasury_plan_idempotency_unique")]


class TreasuryTransferPlanItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(TreasuryTransferPlan, on_delete=models.CASCADE, related_name="items")
    source_account = models.ForeignKey(TreasuryAccount, on_delete=models.PROTECT, related_name="outgoing_plan_items")
    destination_account = models.ForeignKey(TreasuryAccount, on_delete=models.PROTECT, related_name="incoming_plan_items")
    currency_or_asset = models.CharField(max_length=32)
    amount_or_quantity = models.DecimalField(max_digits=30, decimal_places=10)
    priority = models.PositiveSmallIntegerField(default=0)
    reason = models.CharField(max_length=255)
    estimated_available_at = models.DateTimeField()
    state = models.CharField(max_length=24, default="PROPOSED")

    class Meta:
        constraints = [models.CheckConstraint(condition=~models.Q(source_account=models.F("destination_account")), name="treasury_plan_distinct_accounts")]


class LiquidityForecast(SimulationModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("integrations.Organization", on_delete=models.PROTECT)
    institution_id = models.UUIDField()
    currency = models.CharField(max_length=12)
    forecast_time = models.DateTimeField()
    horizon = models.CharField(max_length=24)
    opening_liquidity = models.DecimalField(max_digits=30, decimal_places=10)
    expected_inflows = models.DecimalField(max_digits=30, decimal_places=10)
    expected_outflows = models.DecimalField(max_digits=30, decimal_places=10)
    expected_buffer = models.DecimalField(max_digits=30, decimal_places=10)
    projected_surplus_deficit = models.DecimalField(max_digits=30, decimal_places=10)
    confidence_state = models.CharField(max_length=24)
    policy_version = models.CharField(max_length=64)


class LiquidityStressScenario(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=160)
    scenario_type = models.CharField(max_length=40)
    parameters_json_safe = models.JSONField(default=dict)
    policy_version = models.CharField(max_length=64)
    status = models.CharField(max_length=24, default="SIMULATION")


class LiquidityStressResult(SimulationModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scenario = models.ForeignKey(LiquidityStressScenario, on_delete=models.PROTECT)
    tenant = models.ForeignKey("integrations.Organization", on_delete=models.PROTECT)
    institution_id = models.UUIDField()
    currency = models.CharField(max_length=12)
    starting_liquidity = models.DecimalField(max_digits=30, decimal_places=10)
    peak_shortfall = models.DecimalField(max_digits=30, decimal_places=10)
    minimum_liquidity = models.DecimalField(max_digits=30, decimal_places=10)
    buffer_breach = models.BooleanField(default=False)
    required_funding = models.DecimalField(max_digits=30, decimal_places=10)
    affected_accounts = models.JSONField(default=list)
    calculated_at = models.DateTimeField(auto_now_add=True)


class TreasuryProviderLocationMapping(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    treasury_account = models.ForeignKey(TreasuryAccount, on_delete=models.PROTECT)
    provider_id = models.CharField(max_length=80)
    broker_account_mapping_id = models.UUIDField(null=True, blank=True)
    custody_structure_id = models.UUIDField(null=True, blank=True)
    clearing_relationship_id = models.UUIDField(null=True, blank=True)
    environment = models.CharField(max_length=24, choices=TreasuryAccount.ENVIRONMENTS)
    status = models.CharField(max_length=24, default="REFERENCE_ONLY")
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)


class TreasuryException(SimulationModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("integrations.Organization", on_delete=models.PROTECT)
    institution_id = models.UUIDField()
    treasury_account = models.ForeignKey(TreasuryAccount, null=True, blank=True, on_delete=models.PROTECT)
    exception_type = models.CharField(max_length=48)
    severity = models.CharField(max_length=16)
    state = models.CharField(max_length=24, default="OPEN")
    source_ref = models.CharField(max_length=128)
    detected_at = models.DateTimeField(auto_now_add=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_code = models.CharField(max_length=64, blank=True)
    evidence_hash = models.CharField(max_length=64)


class TreasuryReconciliationRun(SimulationModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("integrations.Organization", on_delete=models.PROTECT)
    status = models.CharField(max_length=24)
    checks = models.JSONField(default=list)
    violations = models.JSONField(default=list)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    candidate_sha = models.CharField(max_length=40)
    policy_version = models.CharField(max_length=64)
