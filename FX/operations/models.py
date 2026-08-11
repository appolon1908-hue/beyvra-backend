import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def uuid4():
    return uuid.uuid4()


class TenantAccountModel(models.Model):
    tenant_id = models.CharField(max_length=120, db_index=True)
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        abstract = True


class ImmutableModel(models.Model):
    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ValidationError("Append-only records cannot be deleted")


class SecurityEvent(TenantAccountModel, ImmutableModel):
    TYPES = [
        (x, x)
        for x in (
            "LOGIN_SUCCESS",
            "LOGIN_FAILURE",
            "PASSWORD_RESET",
            "MFA_ENABLED",
            "MFA_DISABLED",
            "MFA_RESET",
            "SESSION_CREATED",
            "SESSION_REVOKED",
            "NEW_DEVICE",
            "NEW_NETWORK",
            "ACCOUNT_LOCKED",
            "ACCOUNT_UNLOCKED",
            "WITHDRAWAL_ATTEMPT",
            "SUSPICIOUS_ACTIVITY",
        )
    ]
    RISKS = [(x, x) for x in ("LOW", "MEDIUM", "HIGH", "CRITICAL")]
    event_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    event_type = models.CharField(max_length=40, choices=TYPES)
    occurred_at = models.DateTimeField()
    source = models.CharField(max_length=80)
    risk_level = models.CharField(max_length=10, choices=RISKS)
    device_ref = models.UUIDField(null=True, blank=True)
    network_ref = models.CharField(max_length=128, blank=True)
    session_ref = models.UUIDField(null=True, blank=True)
    correlation_id = models.UUIDField(default=uuid4, editable=False)
    metadata_safe = models.JSONField(default=dict)
    resolved = models.BooleanField(default=False)


class DeviceIdentity(TenantAccountModel):
    device_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    device_class = models.CharField(max_length=40)
    trusted = models.BooleanField(default=False)
    revoked = models.BooleanField(default=False)
    risk_state = models.CharField(max_length=16, default="UNKNOWN")
    fingerprint_hash = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "account", "fingerprint_hash"), name="unique_safe_device")
        ]


class AccountSession(TenantAccountModel):
    session_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    device_ref = models.ForeignKey(DeviceIdentity, null=True, blank=True, on_delete=models.SET_NULL)
    auth_strength = models.CharField(max_length=24, default="PASSWORD")
    mfa_verified_at = models.DateTimeField(null=True, blank=True)


class AccountFreeze(TenantAccountModel):
    LEVELS = [(x, x) for x in ("NONE", "PARTIAL", "FULL")]
    level = models.CharField(max_length=10, choices=LEVELS, default="NONE")
    reason_code = models.CharField(max_length=64)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="freeze_actions", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    review_evidence = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "account"), condition=models.Q(released_at__isnull=True), name="one_active_freeze"
            )
        ]


class FraudCase(TenantAccountModel):
    STATUSES = [(x, x) for x in ("OPEN", "IN_REVIEW", "ESCALATED", "RESOLVED", "CLOSED")]
    case_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    case_type = models.CharField(max_length=64)
    risk_level = models.CharField(max_length=10)
    status = models.CharField(max_length=16, choices=STATUSES, default="OPEN")
    reason_codes = models.JSONField(default=list)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="fraud_assignments", on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)


class SupportCase(TenantAccountModel):
    STATUSES = [(x, x) for x in ("OPEN", "PENDING_CUSTOMER", "PENDING_INTERNAL", "ESCALATED", "RESOLVED", "CLOSED")]
    CATEGORIES = [
        (x, x)
        for x in (
            "ACCOUNT_ACCESS",
            "TRADING",
            "MARKET_DATA",
            "DEMO",
            "PAYMENTS",
            "WITHDRAWAL",
            "DEPOSIT",
            "COMPLIANCE",
            "SECURITY",
            "BUG",
            "TECHNICAL",
            "OTHER",
        )
    ]
    case_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    category = models.CharField(max_length=24, choices=CATEGORIES)
    priority = models.CharField(max_length=12, default="NORMAL")
    status = models.CharField(max_length=20, choices=STATUSES, default="OPEN")
    assigned_team = models.CharField(max_length=24, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="support_assignments", on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    safe_summary = models.CharField(max_length=500)


class SupportCaseEvent(TenantAccountModel, ImmutableModel):
    event_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    case = models.ForeignKey(SupportCase, related_name="timeline", on_delete=models.PROTECT)
    event_type = models.CharField(max_length=32)
    visibility = models.CharField(
        max_length=24,
        choices=(("CUSTOMER_VISIBLE_MESSAGE", "CUSTOMER_VISIBLE_MESSAGE"), ("INTERNAL_NOTE", "INTERNAL_NOTE")),
    )
    body_safe = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="support_events", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class TransactionHistoryEntry(TenantAccountModel, ImmutableModel):
    entry_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    type = models.CharField(max_length=20)
    asset = models.CharField(max_length=24)
    amount = models.DecimalField(max_digits=36, decimal_places=18)
    fee = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    status = models.CharField(max_length=24)
    occurred_at = models.DateTimeField()
    settled_at = models.DateTimeField(null=True, blank=True)
    source_ref = models.CharField(max_length=128)
    simulation = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("-occurred_at", "-entry_id")


class ReportJob(TenantAccountModel):
    job_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    report_type = models.CharField(max_length=32)
    parameters_hash = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=128)
    status = models.CharField(max_length=16, default="QUEUED")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    artifact_ref = models.CharField(max_length=255, blank=True)
    reconciliation_passed = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "account", "idempotency_key"), name="unique_report_request")
        ]


class Statement(TenantAccountModel, ImmutableModel):
    statement_id = models.UUIDField(default=uuid4, editable=False)
    version = models.PositiveIntegerField(default=1)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    issued_at = models.DateTimeField(auto_now_add=True)
    simulation = models.BooleanField(default=True)
    reconciliation_passed = models.BooleanField(default=False)
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    correction_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("statement_id", "version"), name="unique_statement_version")]


class LegalHold(TenantAccountModel):
    active = models.BooleanField(default=True)
    reason = models.CharField(max_length=500)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="holds_created", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="holds_released", on_delete=models.PROTECT
    )
    released_at = models.DateTimeField(null=True, blank=True)


class PrivacyExportJob(TenantAccountModel):
    job_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    status = models.CharField(max_length=16, default="QUEUED")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    artifact_ref = models.CharField(max_length=255, blank=True)
    policy_version = models.CharField(max_length=32)
    idempotency_key = models.CharField(max_length=128)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "account", "idempotency_key"), name="unique_privacy_export")
        ]


class Notification(TenantAccountModel):
    notification_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    type = models.CharField(max_length=48)
    category = models.CharField(max_length=16)
    severity = models.CharField(max_length=12, default="INFO")
    channel = models.CharField(max_length=12)
    template_version = models.CharField(max_length=32)
    payload_safe = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default="QUEUED")
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    dedup_key = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField(default=0)
    failure_reason_safe = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "account", "channel", "dedup_key"), name="unique_notification_effect"
            )
        ]


class NotificationPreference(TenantAccountModel):
    category = models.CharField(max_length=16)
    channel = models.CharField(max_length=12)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "account", "category", "channel"), name="unique_notification_preference"
            )
        ]


class OperatorRole(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="operator_roles", on_delete=models.CASCADE)
    tenant_id = models.CharField(max_length=120, db_index=True)
    role = models.CharField(max_length=40)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "tenant_id", "role"), name="unique_operator_role")]


class OperatorActionRequest(ImmutableModel):
    request_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    tenant_id = models.CharField(max_length=120, db_index=True)
    action_type = models.CharField(max_length=64)
    target_ref = models.CharField(max_length=128)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="operator_requests", on_delete=models.PROTECT
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=16, default="PENDING")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="operator_approvals", on_delete=models.PROTECT
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()


class AuditEvent(ImmutableModel):
    audit_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    tenant_id = models.CharField(max_length=120, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    role = models.CharField(max_length=40, blank=True)
    action = models.CharField(max_length=64)
    target = models.CharField(max_length=128)
    reason = models.CharField(max_length=500, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    before_state_hash = models.CharField(max_length=64, blank=True)
    after_state_hash = models.CharField(max_length=64, blank=True)
    metadata_safe = models.JSONField(default=dict)

    def save(self, *args, **kwargs):
        if self.pk and AuditEvent.objects.filter(pk=self.pk).exists():
            raise ValidationError("Audit events are immutable")
        return super().save(*args, **kwargs)


class OutboxEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    tenant_id = models.CharField(max_length=120, db_index=True)
    topic = models.CharField(max_length=80)
    payload_safe = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)


class ProcessedEvent(models.Model):
    event_id = models.UUIDField(primary_key=True)
    consumer = models.CharField(max_length=80)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("event_id", "consumer"), name="unique_inbox_effect")]
