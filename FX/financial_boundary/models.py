import uuid
from django.db import models


class ImmutableFinancialRecord(models.Model):
    """Application guard; PostgreSQL triggers provide the final authority."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError(f"{type(self).__name__} is append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError(f"{type(self).__name__} is append-only")


class ProcessedEvent(models.Model):
    event_id = models.UUIDField(primary_key=True)
    event_type = models.CharField(max_length=128)
    tenant_ref = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "financial_inbox"


class FinancialOutboxEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        IN_FLIGHT = "IN_FLIGHT"
        PUBLISHED = "PUBLISHED"

    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=128)
    schema_version = models.PositiveSmallIntegerField(default=1)
    occurred_at = models.DateTimeField()
    correlation_id = models.UUIDField()
    causation_id = models.UUIDField(null=True, blank=True)
    tenant_ref = models.UUIDField()
    payload = models.JSONField()
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    safe_error_reference = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "financial_outbox"
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="financial_outbox_ready_idx")]


class DeadLetterEvent(models.Model):
    event_id = models.UUIDField(primary_key=True)
    failure_type = models.CharField(max_length=64)
    retry_count = models.PositiveIntegerField(default=0)
    first_failed_at = models.DateTimeField(auto_now_add=True)
    last_failed_at = models.DateTimeField(auto_now=True)
    safe_error_reference = models.CharField(max_length=128)

    class Meta:
        db_table = "financial_dead_letters"


class FinancialAuditEvent(ImmutableFinancialRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=64)
    tenant_ref = models.UUIDField()
    account_ref = models.UUIDField(null=True, blank=True)
    actor_ref = models.UUIDField(null=True, blank=True)
    correlation_id = models.UUIDField()
    subject_ref = models.CharField(max_length=128, blank=True, default="")
    payload_hash = models.CharField(max_length=64)
    safe_metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "financial_audit"
        indexes = [models.Index(fields=["tenant_ref", "occurred_at"], name="financial_audit_tenant_idx")]


class FinancialProjectionCursor(models.Model):
    tenant_ref = models.UUIDField()
    subject_ref = models.CharField(max_length=64)
    event_type = models.CharField(max_length=64)
    last_sequence = models.PositiveBigIntegerField(default=0)
    last_event_id = models.UUIDField(null=True, blank=True)
    snapshot_version = models.PositiveBigIntegerField(default=0)
    projection = models.JSONField(default=dict, blank=True)
    projection_hash = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "financial_projection_cursors"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_ref", "subject_ref", "event_type"],
                name="financial_projection_cursor_scope_unique",
            )
        ]


class FinancialIncident(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    severity = models.CharField(max_length=16)
    type = models.CharField(max_length=64)
    detected_at = models.DateTimeField(auto_now_add=True)
    candidate_sha = models.CharField(max_length=40)
    environment = models.CharField(max_length=24)
    safe_summary = models.CharField(max_length=500)
    status = models.CharField(max_length=24, default="OPEN")
    resolved_at = models.DateTimeField(null=True, blank=True)
    evidence_hash = models.CharField(max_length=64)

    class Meta:
        db_table = "financial_incidents"
