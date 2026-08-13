import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class AccountPlan(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"; ACTIVE = "ACTIVE"; INACTIVE = "INACTIVE"; RETIRED = "RETIRED"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    description_safe = models.TextField(blank=True)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AccountPlanVersion(models.Model):
    plan = models.ForeignKey(AccountPlan, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=AccountPlan.Status.choices, default=AccountPlan.Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="created_plan_versions")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_plan_versions")
    class Meta:
        constraints = [models.UniqueConstraint(fields=("plan", "version"), name="pricing_plan_version_unique")]


class AccountPlanAssignment(models.Model):
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pricing_plan_assignments")
    tenant_ref = models.CharField(max_length=128)
    plan_version = models.ForeignKey(AccountPlanVersion, on_delete=models.PROTECT)
    source = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default="ACTIVE")
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=("account",), condition=Q(effective_to__isnull=True, status="ACTIVE"), name="pricing_one_current_assignment")]


class Entitlement(models.Model):
    class Category(models.TextChoices):
        MARKET_DATA="MARKET_DATA"; NEWS="NEWS"; TRADING="TRADING"; API="API"; REPORTING="REPORTING"; ANALYTICS="ANALYTICS"; SUPPORT="SUPPORT"; FINANCIAL_FEATURE="FINANCIAL_FEATURE"; OTHER="OTHER"
    code = models.CharField(max_length=96, unique=True)
    category = models.CharField(max_length=24, choices=Category.choices)
    description_safe = models.TextField(blank=True)
    status = models.CharField(max_length=16, default="ACTIVE")
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)


class PlanEntitlement(models.Model):
    plan_version = models.ForeignKey(AccountPlanVersion, on_delete=models.PROTECT, related_name="entitlements")
    entitlement = models.ForeignKey(Entitlement, on_delete=models.PROTECT)
    enabled = models.BooleanField(default=False)
    limit_value = models.DecimalField(max_digits=30, decimal_places=8, null=True, blank=True)
    limit_unit = models.CharField(max_length=32, blank=True)
    metadata_safe = models.JSONField(default=dict, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=("plan_version", "entitlement"), name="pricing_plan_entitlement_unique")]


class AccountEntitlementOverride(models.Model):
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    entitlement = models.ForeignKey(Entitlement, on_delete=models.PROTECT)
    override_type = models.CharField(max_length=16, choices=((x,x) for x in ("ENABLE","DISABLE","LIMIT_OVERRIDE")))
    value = models.DecimalField(max_digits=30, decimal_places=8, null=True, blank=True)
    reason_code = models.CharField(max_length=64)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="approved_entitlement_overrides")
    status = models.CharField(max_length=16, default="ACTIVE")


class FeeSchedule(models.Model):
    TYPES = tuple((x,x) for x in ("TRADING_COMMISSION","MAKER","TAKER","WITHDRAWAL","DEPOSIT","TRANSFER","EXCHANGE_PASS_THROUGH","BROKER_PASS_THROUGH","REGULATORY","SUBSCRIPTION","OTHER"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    fee_type = models.CharField(max_length=32, choices=TYPES)
    status = models.CharField(max_length=16, default="DRAFT")
    currency = models.CharField(max_length=12)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    priority = models.IntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class FeeRule(models.Model):
    RATE_TYPES = tuple((x,x) for x in ("FLAT","PERCENT","BASIS_POINTS","PER_SHARE","PER_CONTRACT","PER_UNIT","TIERED"))
    schedule = models.ForeignKey(FeeSchedule, on_delete=models.PROTECT, related_name="rules")
    asset_class = models.CharField(max_length=24, blank=True)
    instrument_ref = models.UUIDField(null=True, blank=True)
    venue_ref = models.CharField(max_length=64, blank=True)
    side = models.CharField(max_length=8, blank=True)
    order_type = models.CharField(max_length=24, blank=True)
    account_plan = models.ForeignKey(AccountPlan, null=True, blank=True, on_delete=models.PROTECT)
    jurisdiction = models.CharField(max_length=8, blank=True)
    min_notional = models.DecimalField(max_digits=30, decimal_places=12, null=True, blank=True)
    max_notional = models.DecimalField(max_digits=30, decimal_places=12, null=True, blank=True)
    rate_type = models.CharField(max_length=16, choices=RATE_TYPES)
    rate_value = models.DecimalField(max_digits=30, decimal_places=12)
    min_fee = models.DecimalField(max_digits=30, decimal_places=12, null=True, blank=True)
    max_fee = models.DecimalField(max_digits=30, decimal_places=12, null=True, blank=True)
    currency = models.CharField(max_length=12)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    rule_version = models.PositiveIntegerField()
    is_rebate = models.BooleanField(default=False)
    class Meta:
        indexes = [models.Index(fields=("asset_class", "effective_from"), name="pricing_fee_lookup")]
    def clean(self):
        if self.rate_value < 0 and not self.is_rebate:
            raise ValidationError("Negative fees require an explicit rebate rule.")


class PricingRoundingPolicy(models.Model):
    currency = models.CharField(max_length=12)
    decimal_places = models.PositiveSmallIntegerField()
    rounding_mode = models.CharField(max_length=24)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)


class SubscriptionPrice(models.Model):
    plan_version = models.ForeignKey(AccountPlanVersion, on_delete=models.PROTECT)
    billing_period = models.CharField(max_length=16, choices=((x,x) for x in ("MONTHLY","ANNUAL","CUSTOM")))
    currency = models.CharField(max_length=12)
    amount = models.DecimalField(max_digits=30, decimal_places=12)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, default="DRAFT")


class PricingPromotion(models.Model):
    code = models.CharField(max_length=64, unique=True)
    promotion_type = models.CharField(max_length=24)
    value = models.DecimalField(max_digits=30, decimal_places=12)
    eligible_plan = models.ForeignKey(AccountPlan, null=True, blank=True, on_delete=models.PROTECT)
    effective_from = models.DateTimeField(); effective_to = models.DateTimeField()
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, default="DRAFT")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)


class FeeWaiver(models.Model):
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fee_type = models.CharField(max_length=32)
    reason = models.CharField(max_length=96)
    effective_from = models.DateTimeField(); effective_to = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="approved_fee_waivers")
    audit_ref = models.UUIDField(default=uuid.uuid4)


class PricingAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=64)
    entity_ref = models.CharField(max_length=128)
    actor_ref = models.CharField(max_length=128)
    occurred_at = models.DateTimeField()
    evidence_hash = models.CharField(max_length=64)
    metadata_safe = models.JSONField(default=dict, blank=True)
