import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from integrations.models import Organization
from .domain import AccountStatus, AllocationMethod, CustodyModel, Environment, choices


ACCOUNT_TYPES = ("INSTITUTIONAL", "FUND", "ASSET_MANAGER", "BROKER_DEALER_REFERENCE", "CORPORATE", "FAMILY_OFFICE", "PROFESSIONAL_TRADER", "INTERNAL_TEST")
SUBACCOUNT_TYPES = ("TRADING", "STRATEGY", "PORTFOLIO", "CLIENT", "FUND", "SLEEVE", "HOUSE_REFERENCE", "SETTLEMENT_REFERENCE", "TEST")
OWNER_TYPES = ("LEGAL_ENTITY", "BENEFICIAL_OWNER_REFERENCE", "FUND", "CLIENT", "HOUSE", "UNKNOWN")
RELATIONSHIP_TYPES = ("CARRYING", "CLEARING", "PRIME", "INTRODUCING_REFERENCE", "CUSTODY_REFERENCE", "SETTLEMENT_REFERENCE")
ACCOUNT_ROLES = ("EXECUTION", "CLEARING", "CUSTODY", "SETTLEMENT", "OMNIBUS", "SEGREGATED")
CAPABILITIES = ("PAPER_EXECUTION", "CLEARING_REFERENCE", "CUSTODY_REFERENCE", "SETTLEMENT_REFERENCE", "LIVE_EXECUTION", "MARGIN", "SHORTING", "OMNIBUS", "SEGREGATED", "DVP", "FOP")
SETTLEMENT_MODELS = ("INTERNAL_SIMULATION", "OMNIBUS_REFERENCE", "SEGREGATED_REFERENCE", "DVP_REFERENCE", "FOP_REFERENCE")


class EffectiveModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def clean(self):
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValidationError("EFFECTIVE_DATE_RANGE_INVALID")


class InstitutionalAccount(EffectiveModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="institutional_accounts")
    institution_code = models.CharField(max_length=40)
    display_name = models.CharField(max_length=160)
    legal_entity_ref = models.CharField(max_length=255, blank=True, default="")
    account_type = models.CharField(max_length=32, choices=[(x, x) for x in ACCOUNT_TYPES])
    status = models.CharField(max_length=16, choices=choices(AccountStatus), default=AccountStatus.PENDING)
    base_currency = models.CharField(max_length=3)
    jurisdiction_ref = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("tenant", "institution_code"), name="unique_institution_code_per_tenant")]
        indexes = [models.Index(fields=("tenant", "status"), name="institution_tenant_status_idx")]


class InstitutionalSubaccount(EffectiveModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="subaccounts")
    tenant = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="institutional_subaccounts")
    parent_subaccount = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    code = models.CharField(max_length=40)
    display_name = models.CharField(max_length=160)
    subaccount_type = models.CharField(max_length=32, choices=[(x, x) for x in SUBACCOUNT_TYPES])
    base_currency = models.CharField(max_length=3)
    status = models.CharField(max_length=16, choices=choices(AccountStatus), default=AccountStatus.PENDING)
    risk_profile_ref = models.CharField(max_length=255, blank=True, default="")
    trading_policy_ref = models.CharField(max_length=255, blank=True, default="")
    allocation_eligible = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("institution", "code"), name="unique_subaccount_code_per_institution")]
        indexes = [models.Index(fields=("tenant", "institution", "status"), name="subaccount_scope_status_idx")]

    def clean(self):
        super().clean()
        if self.tenant_id != self.institution.tenant_id:
            raise ValidationError("SUBACCOUNT_WRONG_TENANT")
        if self.parent_subaccount_id:
            if self.parent_subaccount_id == self.id:
                raise ValidationError("SUBACCOUNT_SELF_PARENT")
            if self.parent_subaccount.tenant_id != self.tenant_id or self.parent_subaccount.institution_id != self.institution_id:
                raise ValidationError("CROSS_INSTITUTION_SUBACCOUNT_LINK")
            seen = {self.id}
            node = self.parent_subaccount
            for _ in range(32):
                if node.id in seen:
                    raise ValidationError("SUBACCOUNT_HIERARCHY_CYCLE")
                seen.add(node.id)
                if not node.parent_subaccount_id:
                    return
                node = node.parent_subaccount
            raise ValidationError("SUBACCOUNT_HIERARCHY_DEPTH_EXCEEDED")


class AccountOwnerReference(EffectiveModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="owner_references")
    subaccount = models.ForeignKey(InstitutionalSubaccount, null=True, blank=True, on_delete=models.PROTECT, related_name="owner_references")
    owner_type = models.CharField(max_length=32, choices=[(x, x) for x in OWNER_TYPES])
    external_authority = models.CharField(max_length=80)
    external_owner_ref = models.CharField(max_length=255)
    ownership_role = models.CharField(max_length=80)
    status = models.CharField(max_length=16, choices=choices(AccountStatus), default=AccountStatus.PENDING)

    def clean(self):
        super().clean()
        if self.subaccount_id and self.subaccount.institution_id != self.institution_id:
            raise ValidationError("CROSS_INSTITUTION_OWNER_REFERENCE")
        if not self.external_authority or not self.external_owner_ref:
            raise ValidationError("AUTHORITATIVE_OWNER_REFERENCE_REQUIRED")


class CustodyStructure(EffectiveModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="custody_structures")
    custody_model = models.CharField(max_length=32, choices=choices(CustodyModel), default=CustodyModel.UNKNOWN)
    provider = models.CharField(max_length=80, blank=True, default="")
    status = models.CharField(max_length=16, choices=choices(AccountStatus), default=AccountStatus.PENDING)
    policy_version = models.CharField(max_length=32)


class CustodyPolicy(EffectiveModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    custody_structure = models.ForeignKey(CustodyStructure, on_delete=models.PROTECT, related_name="policies")
    asset_class = models.CharField(max_length=32)
    asset = models.CharField(max_length=32, blank=True, default="")
    segregation_required = models.BooleanField(default=False)
    omnibus_permitted = models.BooleanField(default=False)
    provider_account_required = models.BooleanField(default=False)
    subledger_required = models.BooleanField(default=True)
    policy_version = models.CharField(max_length=32)


class OmnibusAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="omnibus_accounts")
    custody_structure = models.ForeignKey(CustodyStructure, on_delete=models.PROTECT, related_name="omnibus_accounts")
    provider_id = models.CharField(max_length=80, blank=True, default="")
    external_account_ref = models.CharField(max_length=255, blank=True, default="")
    asset_class = models.CharField(max_length=32)
    currency = models.CharField(max_length=3, blank=True, default="")
    status = models.CharField(max_length=16, choices=choices(AccountStatus), default=AccountStatus.PENDING)
    environment = models.CharField(max_length=24, choices=choices(Environment))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class OmnibusBeneficialPosition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    omnibus_account = models.ForeignKey(OmnibusAccount, on_delete=models.PROTECT, related_name="beneficial_positions")
    subaccount = models.ForeignKey(InstitutionalSubaccount, on_delete=models.PROTECT, related_name="omnibus_positions")
    instrument_id = models.CharField(max_length=80)
    quantity = models.DecimalField(max_digits=36, decimal_places=18)
    as_of = models.DateTimeField()
    source_version = models.CharField(max_length=64)
    simulation = models.BooleanField(default=True, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("omnibus_account", "subaccount", "instrument_id", "source_version"), name="unique_omnibus_position_version")]


class OmnibusCashAttribution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    omnibus_account = models.ForeignKey(OmnibusAccount, on_delete=models.PROTECT, related_name="cash_attributions")
    subaccount = models.ForeignKey(InstitutionalSubaccount, on_delete=models.PROTECT, related_name="omnibus_cash")
    currency = models.CharField(max_length=3)
    amount = models.DecimalField(max_digits=36, decimal_places=18)
    as_of = models.DateTimeField()
    simulation = models.BooleanField(default=True, editable=False)


class SegregatedCustodyAccount(EffectiveModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="segregated_accounts")
    subaccount = models.ForeignKey(InstitutionalSubaccount, on_delete=models.PROTECT, related_name="segregated_accounts")
    provider_id = models.CharField(max_length=80, blank=True, default="")
    external_account_ref = models.CharField(max_length=255, blank=True, default="")
    custody_structure = models.ForeignKey(CustodyStructure, on_delete=models.PROTECT, related_name="segregated_accounts")
    status = models.CharField(max_length=16, choices=choices(AccountStatus), default=AccountStatus.PENDING)
    environment = models.CharField(max_length=24, choices=choices(Environment))

    class Meta:
        constraints = [models.UniqueConstraint(fields=("provider_id", "external_account_ref"), condition=models.Q(status="ACTIVE") & ~models.Q(external_account_ref=""), name="unique_active_segregated_provider_account")]


class AllocationGroup(EffectiveModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="allocation_groups")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    allocation_method = models.CharField(max_length=32, choices=choices(AllocationMethod))
    status = models.CharField(max_length=16, choices=choices(AccountStatus), default=AccountStatus.PENDING)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("institution", "code"), name="unique_allocation_group_code")]


class AllocationGroupMember(EffectiveModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    allocation_group = models.ForeignKey(AllocationGroup, on_delete=models.PROTECT, related_name="members")
    subaccount = models.ForeignKey(InstitutionalSubaccount, on_delete=models.PROTECT, related_name="allocation_memberships")
    weight = models.DecimalField(max_digits=20, decimal_places=18, null=True, blank=True)
    fixed_quantity = models.DecimalField(max_digits=36, decimal_places=18, null=True, blank=True)
    priority = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=choices(AccountStatus), default=AccountStatus.PENDING)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("allocation_group", "subaccount"), name="unique_allocation_group_member"),
            models.CheckConstraint(condition=models.Q(weight__isnull=True) | (models.Q(weight__gt=0) & models.Q(weight__lte=1)), name="valid_allocation_weight"),
        ]

    def clean(self):
        super().clean()
        if self.subaccount.institution_id != self.allocation_group.institution_id:
            raise ValidationError("CROSS_INSTITUTION_ALLOCATION_MEMBER")


class InstitutionalTradeAllocationInstruction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="trade_allocations")
    trade_id = models.CharField(max_length=128)
    allocation_group = models.ForeignKey(AllocationGroup, null=True, blank=True, on_delete=models.PROTECT, related_name="instructions")
    source_account = models.ForeignKey(InstitutionalSubaccount, on_delete=models.PROTECT, related_name="source_allocations")
    allocation_method = models.CharField(max_length=32, choices=choices(AllocationMethod))
    state = models.CharField(max_length=16, choices=[(x, x) for x in ("DRAFT", "CALCULATED", "VALIDATED", "ALLOCATED", "EXCEPTION", "REVERSED")], default="DRAFT")
    policy_version = models.CharField(max_length=32)
    canonical_quantity = models.DecimalField(max_digits=36, decimal_places=18)
    idempotency_key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("institution", "trade_id"), name="one_allocation_per_institution_trade"), models.UniqueConstraint(fields=("institution", "idempotency_key"), name="unique_institution_allocation_idempotency")]


class InstitutionalTradeAllocationLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instruction = models.ForeignKey(InstitutionalTradeAllocationInstruction, on_delete=models.PROTECT, related_name="lines")
    target_subaccount = models.ForeignKey(InstitutionalSubaccount, on_delete=models.PROTECT, related_name="allocation_lines")
    quantity = models.DecimalField(max_digits=36, decimal_places=18)
    notional = models.DecimalField(max_digits=36, decimal_places=18)
    fee_share = models.DecimalField(max_digits=36, decimal_places=18, null=True, blank=True)
    status = models.CharField(max_length=16, default="PENDING")

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="positive_allocation_quantity")]


class ClearingBroker(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=160)
    status = models.CharField(max_length=16, choices=choices(AccountStatus), default=AccountStatus.PENDING)
    environment = models.CharField(max_length=24, choices=choices(Environment))
    supported_asset_classes = models.JSONField(default=list)
    external_reference_safe = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ClearingBrokerRelationship(EffectiveModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="clearing_relationships")
    clearing_broker = models.ForeignKey(ClearingBroker, on_delete=models.PROTECT, related_name="relationships")
    relationship_type = models.CharField(max_length=32, choices=[(x, x) for x in RELATIONSHIP_TYPES])
    status = models.CharField(max_length=16, choices=choices(AccountStatus), default=AccountStatus.PENDING)
    approved_for_paper = models.BooleanField(default=False)
    approved_for_live = models.BooleanField(default=False, editable=False)


class BrokerAccountMapping(EffectiveModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="broker_account_mappings")
    subaccount = models.ForeignKey(InstitutionalSubaccount, null=True, blank=True, on_delete=models.PROTECT, related_name="broker_account_mappings")
    execution_provider_id = models.CharField(max_length=80)
    clearing_broker = models.ForeignKey(ClearingBroker, null=True, blank=True, on_delete=models.PROTECT, related_name="account_mappings")
    provider_account_ref = models.CharField(max_length=255)
    account_role = models.CharField(max_length=16, choices=[(x, x) for x in ACCOUNT_ROLES])
    environment = models.CharField(max_length=24, choices=choices(Environment))
    status = models.CharField(max_length=16, choices=choices(AccountStatus), default=AccountStatus.PENDING)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("execution_provider_id", "provider_account_ref", "account_role"), condition=models.Q(status="ACTIVE"), name="unique_active_broker_account_role")]


class ClearingAccountCapability(EffectiveModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    broker_account_mapping = models.ForeignKey(BrokerAccountMapping, on_delete=models.PROTECT, related_name="capabilities")
    asset_class = models.CharField(max_length=32)
    capability = models.CharField(max_length=32, choices=[(x, x) for x in CAPABILITIES])
    enabled = models.BooleanField(default=False)
    environment = models.CharField(max_length=24, choices=choices(Environment))
    source = models.CharField(max_length=80)
    verified_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        super().clean()
        if self.capability in {"LIVE_EXECUTION", "MARGIN", "SHORTING", "OMNIBUS", "SEGREGATED", "DVP", "FOP"} and self.enabled:
            raise ValidationError("LIVE_CLEARING_CAPABILITY_DISABLED")


class InstitutionalSettlementMapping(EffectiveModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="settlement_mappings")
    subaccount = models.ForeignKey(InstitutionalSubaccount, null=True, blank=True, on_delete=models.PROTECT, related_name="settlement_mappings")
    asset_class = models.CharField(max_length=32)
    currency = models.CharField(max_length=3, blank=True, default="")
    custody_structure = models.ForeignKey(CustodyStructure, on_delete=models.PROTECT, related_name="settlement_mappings")
    broker_account_mapping = models.ForeignKey(BrokerAccountMapping, null=True, blank=True, on_delete=models.PROTECT, related_name="settlement_mappings")
    settlement_model = models.CharField(max_length=32, choices=[(x, x) for x in SETTLEMENT_MODELS])
    status = models.CharField(max_length=16, choices=choices(AccountStatus), default=AccountStatus.PENDING)


class InstitutionalPosition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Organization, on_delete=models.PROTECT)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="positions")
    subaccount = models.ForeignKey(InstitutionalSubaccount, on_delete=models.PROTECT, related_name="positions")
    instrument_id = models.CharField(max_length=80)
    quantity = models.DecimalField(max_digits=36, decimal_places=18)
    as_of = models.DateTimeField()
    simulation = models.BooleanField(default=True, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("subaccount", "instrument_id"), name="unique_institutional_position")]


class InstitutionalAuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    event_type = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_ref = models.CharField(max_length=128)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk and InstitutionalAuditEvent.objects.filter(pk=self.pk).exists():
            raise ValueError("INSTITUTIONAL_AUDIT_IS_APPEND_ONLY")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("INSTITUTIONAL_AUDIT_IS_APPEND_ONLY")


class InstitutionalOutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT)
    event_type = models.CharField(max_length=100)
    aggregate_ref = models.CharField(max_length=128)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)


class InstitutionalInboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=80)
    event_id = models.CharField(max_length=255)
    payload_hash = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("source", "event_id"), name="unique_institutional_inbox_event")]


class InstitutionalReconciliationRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="reconciliation_runs")
    status = models.CharField(max_length=16, default="COMPLETED")
    violations = models.JSONField(default=list)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class InstitutionalOperatorAction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(InstitutionalAccount, on_delete=models.PROTECT, related_name="operator_actions")
    control = models.CharField(max_length=80)
    payload = models.JSONField(default=dict)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="institutional_actions_requested")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="institutional_actions_approved")
    status = models.CharField(max_length=16, default="PENDING")
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(approved_by__isnull=True) | ~models.Q(approved_by=models.F("requested_by")), name="institutional_independent_checker")]
