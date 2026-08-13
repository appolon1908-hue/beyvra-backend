import uuid

from django.db import models


MONEY = {"max_digits": 36, "decimal_places": 18}


class ImmutableModel(models.Model):
    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ValueError("VALUATION_EVIDENCE_APPEND_ONLY")

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("VALUATION_EVIDENCE_IMMUTABLE")
        return super().save(*args, **kwargs)


class ValuationPrice(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instrument_id = models.CharField(max_length=64)
    valuation_time = models.DateTimeField()
    price = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=16)
    price_type = models.CharField(max_length=32)
    provider_id = models.CharField(max_length=64)
    market_data_ref = models.CharField(max_length=128)
    quality_state = models.CharField(max_length=16)
    market_status = models.CharField(max_length=24)
    policy_id = models.CharField(max_length=64)
    policy_version = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("instrument_id", "valuation_time", "price_type", "provider_id", "market_data_ref"), name="valuation_price_evidence_unique")]
        indexes = [models.Index(fields=("instrument_id", "valuation_time"), name="valuation_price_time_idx")]


class FxValuationRate(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base_currency = models.CharField(max_length=16)
    quote_currency = models.CharField(max_length=16)
    rate = models.DecimalField(**MONEY)
    rate_time = models.DateTimeField()
    provider_id = models.CharField(max_length=64)
    source_ref = models.CharField(max_length=128)
    quality_state = models.CharField(max_length=16)
    policy_version = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("base_currency", "quote_currency", "rate_time", "provider_id", "source_ref"), name="valuation_fx_evidence_unique")]


class TaxLot(models.Model):
    STATES = ("OPEN", "PARTIALLY_DISPOSED", "CLOSED", "ADJUSTED", "REVERSED")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    instrument_id = models.CharField(max_length=64)
    acquisition_trade = models.OneToOneField("post_trade.Trade", null=True, blank=True, on_delete=models.PROTECT, related_name="tax_lot")
    acquisition_date = models.DateField()
    original_quantity = models.DecimalField(**MONEY)
    remaining_quantity = models.DecimalField(**MONEY)
    unit_cost = models.DecimalField(**MONEY)
    total_cost = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=16)
    source_type = models.CharField(max_length=24)
    status = models.CharField(max_length=24, choices=[(v, v) for v in STATES])
    policy_version = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("tenant_ref", "account_ref", "instrument_id", "acquisition_date"), name="valuation_lot_fifo_idx")]


class TaxLotDisposition(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lot = models.ForeignKey(TaxLot, on_delete=models.PROTECT, related_name="dispositions")
    disposal_trade = models.ForeignKey("post_trade.Trade", on_delete=models.PROTECT, related_name="lot_dispositions")
    quantity = models.DecimalField(**MONEY)
    allocated_basis = models.DecimalField(**MONEY)
    proceeds = models.DecimalField(**MONEY)
    realized_gain_loss = models.DecimalField(**MONEY)
    disposed_at = models.DateTimeField()
    selection_method = models.CharField(max_length=40)
    policy_version = models.CharField(max_length=32)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("lot", "disposal_trade"), name="valuation_lot_disposal_unique")]


class CostBasisPosition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    instrument_id = models.CharField(max_length=64)
    quantity = models.DecimalField(**MONEY)
    gross_cost = models.DecimalField(**MONEY)
    allocated_fees = models.DecimalField(**MONEY)
    adjustments = models.DecimalField(**MONEY)
    total_cost_basis = models.DecimalField(**MONEY)
    average_unit_cost = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=16)
    policy_version = models.CharField(max_length=32)
    as_of = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("tenant_ref", "account_ref", "instrument_id"), name="valuation_cost_basis_unique")]


class RealizedPnLEvent(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    instrument_id = models.CharField(max_length=64)
    disposal_trade = models.OneToOneField("post_trade.Trade", on_delete=models.PROTECT, related_name="realized_pnl")
    quantity = models.DecimalField(**MONEY)
    proceeds = models.DecimalField(**MONEY)
    allocated_cost_basis = models.DecimalField(**MONEY)
    fees = models.DecimalField(**MONEY)
    realized_pnl = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=16)
    base_currency_pnl = models.DecimalField(**MONEY)
    lot_method = models.CharField(max_length=40)
    policy_version = models.CharField(max_length=32)
    realized_at = models.DateTimeField()
    simulation = models.BooleanField(default=True)


class PositionValuation(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    institution_ref = models.CharField(max_length=128, blank=True)
    subaccount_ref = models.CharField(max_length=128, blank=True)
    instrument_id = models.CharField(max_length=64)
    quantity = models.DecimalField(**MONEY)
    valuation_price = models.DecimalField(**MONEY)
    price_currency = models.CharField(max_length=16)
    market_value = models.DecimalField(**MONEY)
    base_currency_value = models.DecimalField(**MONEY)
    valuation_time = models.DateTimeField()
    price_ref = models.ForeignKey(ValuationPrice, on_delete=models.PROTECT)
    fx_ref = models.ForeignKey(FxValuationRate, null=True, blank=True, on_delete=models.PROTECT)
    quality_state = models.CharField(max_length=16)
    policy_version = models.CharField(max_length=32)
    simulation = models.BooleanField(default=True)


class UnrealizedPnLSnapshot(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    instrument_id = models.CharField(max_length=64)
    quantity = models.DecimalField(**MONEY)
    remaining_cost_basis = models.DecimalField(**MONEY)
    market_value = models.DecimalField(**MONEY)
    unrealized_pnl = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=16)
    base_currency_pnl = models.DecimalField(**MONEY)
    valuation_time = models.DateTimeField()
    quality_state = models.CharField(max_length=16)
    policy_version = models.CharField(max_length=32)


class PortfolioNavSnapshot(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    base_currency = models.CharField(max_length=16)
    cash_value = models.DecimalField(**MONEY)
    position_value = models.DecimalField(**MONEY)
    receivables = models.DecimalField(**MONEY)
    payables = models.DecimalField(**MONEY)
    fees_accrued = models.DecimalField(**MONEY)
    total_assets = models.DecimalField(**MONEY)
    total_liabilities = models.DecimalField(**MONEY)
    nav = models.DecimalField(**MONEY)
    valuation_time = models.DateTimeField()
    quality_state = models.CharField(max_length=16)
    policy_version = models.CharField(max_length=32)
    simulation = models.BooleanField(default=True)


class InstitutionalNavSnapshot(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_ref = models.CharField(max_length=128)
    base_currency = models.CharField(max_length=16)
    subaccount_nav_total = models.DecimalField(**MONEY)
    institution_level_adjustments = models.DecimalField(**MONEY)
    nav = models.DecimalField(**MONEY)
    valuation_time = models.DateTimeField()
    quality_state = models.CharField(max_length=16)
    policy_version = models.CharField(max_length=32)
    simulation = models.BooleanField(default=True)


class PortfolioIncomeExpenseEvent(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    instrument_id = models.CharField(max_length=64, blank=True)
    event_type = models.CharField(max_length=32)
    amount = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=16)
    source_ref = models.CharField(max_length=128)
    effective_at = models.DateTimeField()
    policy_version = models.CharField(max_length=32)
    simulation = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("event_type", "source_ref"), name="valuation_income_source_unique")]


class CostBasisAdjustment(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    instrument_id = models.CharField(max_length=64)
    tax_lot = models.ForeignKey(TaxLot, null=True, blank=True, on_delete=models.PROTECT)
    corporate_action_ref = models.CharField(max_length=128)
    adjustment_type = models.CharField(max_length=32)
    quantity_delta = models.DecimalField(**MONEY)
    basis_delta = models.DecimalField(**MONEY)
    reason = models.CharField(max_length=255)
    effective_at = models.DateTimeField()
    policy_version = models.CharField(max_length=32)


class PerformanceSnapshot(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    opening_value = models.DecimalField(**MONEY)
    closing_value = models.DecimalField(**MONEY)
    external_flows = models.DecimalField(**MONEY)
    income = models.DecimalField(**MONEY)
    fees = models.DecimalField(**MONEY)
    pnl = models.DecimalField(**MONEY)
    return_value = models.DecimalField(**MONEY)
    return_method = models.CharField(max_length=32)
    quality_state = models.CharField(max_length=16)
    policy_version = models.CharField(max_length=32)


class PerformanceAttribution(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    dimension = models.CharField(max_length=32)
    dimension_value = models.CharField(max_length=128)
    opening_value = models.DecimalField(**MONEY)
    pnl_contribution = models.DecimalField(**MONEY)
    return_contribution = models.DecimalField(**MONEY)
    fees = models.DecimalField(**MONEY)
    income = models.DecimalField(**MONEY)
    policy_version = models.CharField(max_length=32)
    quality_state = models.CharField(max_length=16)


class PortfolioBenchmarkAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    scope_ref = models.CharField(max_length=128)
    benchmark_ref = models.CharField(max_length=128)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    policy_version = models.CharField(max_length=32)


class ValuationSnapshot(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    scope_type = models.CharField(max_length=16)
    scope_ref = models.CharField(max_length=128)
    valuation_time = models.DateTimeField()
    base_currency = models.CharField(max_length=16)
    market_data_cutoff = models.DateTimeField()
    policy_versions = models.JSONField(default=dict)
    position_count = models.PositiveIntegerField()
    cash_value = models.DecimalField(**MONEY)
    position_value = models.DecimalField(**MONEY)
    nav = models.DecimalField(**MONEY)
    realized_pnl = models.DecimalField(**MONEY)
    unrealized_pnl = models.DecimalField(**MONEY)
    quality_state = models.CharField(max_length=16)
    evidence_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)


class ValuationCorrection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_snapshot = models.ForeignKey(ValuationSnapshot, null=True, blank=True, on_delete=models.PROTECT)
    correction_type = models.CharField(max_length=40)
    source_ref = models.CharField(max_length=128)
    reason_code = models.CharField(max_length=64)
    effective_at = models.DateTimeField()
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    created_by = models.CharField(max_length=128)
    approved_by = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=16, default="PENDING")


class ValuationAudit(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    actor_ref = models.CharField(max_length=128)
    action = models.CharField(max_length=128)
    resource_type = models.CharField(max_length=64)
    resource_ref = models.CharField(max_length=128)
    evidence_hash = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()


class ValuationReconciliationRun(ImmutableModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField()
    status = models.CharField(max_length=16)
    checks = models.JSONField(default=dict)
    violations = models.JSONField(default=list)
    policy_version = models.CharField(max_length=32)
