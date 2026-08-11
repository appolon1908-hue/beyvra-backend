import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


EVENT_TYPES = (
    "SELF_TRADE_ATTEMPT", "WASH_TRADE_PATTERN", "SPOOFING_INDICATOR",
    "LAYERING_INDICATOR", "EXCESSIVE_CANCEL_PATTERN", "RAPID_ORDER_FLIP",
    "MARKET_CLOSE_ORDER_PATTERN", "RESTRICTED_INSTRUMENT_ATTEMPT",
    "ACCOUNT_RESTRICTION_VIOLATION", "PRICE_DEVIATION_ORDER",
    "VOLUME_ANOMALY_ORDER", "ORDER_RATE_ANOMALY",
    "CROSS_ACCOUNT_COORDINATION_INDICATOR", "SUSPICIOUS_POSITION_BUILDUP",
    "OTHER_REVIEW_REQUIRED",
)


class SurveillanceRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    event_type = models.CharField(max_length=64, choices=[(v, v) for v in EVENT_TYPES])
    enabled = models.BooleanField(default=True)
    severity = models.CharField(max_length=16, choices=[(v, v) for v in ("LOW", "MEDIUM", "HIGH", "CRITICAL")])
    asset_class = models.CharField(max_length=32, default="ALL")
    parameters_json_safe = models.JSONField(default=dict)
    policy_version = models.CharField(max_length=32)
    version = models.PositiveIntegerField(default=1)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("name", "version"), name="surveillance_rule_version_unique"),
            models.UniqueConstraint(fields=("name",), condition=Q(effective_to__isnull=True), name="surveillance_one_current_rule"),
        ]
        indexes = [models.Index(fields=("event_type", "effective_from"), name="surv_rule_effective_idx")]

    def clean(self):
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValidationError("effective_to must follow effective_from")


class TradingRestriction(models.Model):
    SCOPE_TYPES = ("ACCOUNT", "TENANT", "INSTRUMENT", "ASSET_CLASS", "VENUE", "JURISDICTION")
    TYPES = ("BLOCK_NEW_ORDERS", "CANCEL_ONLY", "CLOSE_ONLY", "BLOCK_BUYS", "BLOCK_SELLS", "BLOCK_INSTRUMENT", "BLOCK_ASSET_CLASS", "BLOCK_VENUE", "REVIEW_REQUIRED")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    scope_type = models.CharField(max_length=16, choices=[(v, v) for v in SCOPE_TYPES])
    scope_ref = models.CharField(max_length=128)
    restriction_type = models.CharField(max_length=32, choices=[(v, v) for v in TYPES])
    reason_code = models.CharField(max_length=64)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=128)
    approved_by = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=16, choices=[(v, v) for v in ("PENDING", "ACTIVE", "REMOVED", "EXPIRED", "REJECTED")], default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=("tenant_ref", "scope_type", "scope_ref", "status"), name="surv_restriction_scope_idx"),
            models.Index(fields=("effective_from", "effective_to"), name="surv_restriction_time_idx"),
        ]

    def clean(self):
        if self.approved_by and self.approved_by == self.created_by:
            raise ValidationError("maker cannot approve own restriction")
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValidationError("effective_to must follow effective_from")


class SurveillanceEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    instrument_id = models.CharField(max_length=64)
    event_type = models.CharField(max_length=64, choices=[(v, v) for v in EVENT_TYPES])
    severity = models.CharField(max_length=16)
    detected_at = models.DateTimeField()
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    rule = models.ForeignKey(SurveillanceRule, on_delete=models.PROTECT)
    rule_version = models.PositiveIntegerField()
    policy_version = models.CharField(max_length=32)
    score = models.DecimalField(max_digits=8, decimal_places=5)
    status = models.CharField(max_length=16, choices=[(v, v) for v in ("OPEN", "REVIEWING", "ESCALATED", "RESOLVED", "DISMISSED")], default="OPEN")
    evidence_hash = models.CharField(max_length=64)
    evidence_safe = models.JSONField(default=dict)
    source_event_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("source_event_id", "rule"), condition=Q(source_event_id__isnull=False), name="surveillance_source_rule_unique")]
        indexes = [
            models.Index(fields=("tenant_ref", "account_ref", "detected_at"), name="surv_event_account_idx"),
            models.Index(fields=("instrument_id", "event_type", "detected_at"), name="surv_event_instrument_idx"),
            models.Index(fields=("status", "severity", "detected_at"), name="surv_event_status_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values("tenant_ref", "account_ref", "instrument_id", "event_type", "detected_at", "window_start", "window_end", "rule_id", "rule_version", "policy_version", "score", "evidence_hash", "evidence_safe", "source_event_id").first()
            if previous:
                for field, old_value in previous.items():
                    if getattr(self, field) != old_value:
                        raise ValueError("SURVEILLANCE_EVIDENCE_APPEND_ONLY")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("SURVEILLANCE_EVIDENCE_APPEND_ONLY")


class SurveillanceCase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    case_type = models.CharField(max_length=64)
    severity = models.CharField(max_length=16)
    status = models.CharField(max_length=16, choices=[(v, v) for v in ("OPEN", "IN_REVIEW", "ESCALATED", "RESTRICTED", "RESOLVED", "CLOSED")], default="OPEN")
    assigned_to = models.CharField(max_length=128, blank=True)
    opened_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_code = models.CharField(max_length=64, blank=True)
    policy_version = models.CharField(max_length=32)
    evidence_hash = models.CharField(max_length=64)
    events = models.ManyToManyField(SurveillanceEvent, related_name="cases")

    class Meta:
        indexes = [models.Index(fields=("tenant_ref", "status", "opened_at"), name="surv_case_status_idx")]


class SurveillanceCaseEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(SurveillanceCase, on_delete=models.PROTECT, related_name="timeline")
    event_type = models.CharField(max_length=32, choices=[(v, v) for v in ("CASE_OPENED", "CASE_ASSIGNED", "CASE_ESCALATED", "CASE_RESOLVED", "CASE_CLOSED", "NOTE_ADDED")])
    actor_ref = models.CharField(max_length=128)
    reason = models.CharField(max_length=255)
    evidence_hash = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=("case", "occurred_at"), name="surv_case_timeline_idx")]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("SURVEILLANCE_CASE_EVENT_APPEND_ONLY")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("SURVEILLANCE_CASE_EVENT_APPEND_ONLY")


class SurveillanceAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    actor_ref = models.CharField(max_length=128)
    action = models.CharField(max_length=128)
    resource_type = models.CharField(max_length=64)
    resource_ref = models.CharField(max_length=128)
    reason = models.CharField(max_length=255)
    evidence_hash = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=("tenant_ref", "resource_type", "resource_ref", "occurred_at"), name="surv_audit_resource_idx")]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("SURVEILLANCE_AUDIT_APPEND_ONLY")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("SURVEILLANCE_AUDIT_APPEND_ONLY")


class SurveillanceDeadLetter(models.Model):
    event_id = models.UUIDField()
    tenant_ref = models.CharField(max_length=128)
    event_type = models.CharField(max_length=128)
    failure_category = models.CharField(max_length=64)
    retry_count = models.PositiveIntegerField(default=0)
    first_failed_at = models.DateTimeField()
    last_failed_at = models.DateTimeField()
    safe_error_ref = models.UUIDField(default=uuid.uuid4, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("event_id", "event_type"), name="surveillance_dead_letter_unique")]
