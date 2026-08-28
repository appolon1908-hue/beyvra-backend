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


class ProviderWebhookInbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        PROCESSING = "PROCESSING"
        PROCESSED = "PROCESSED"
        DEAD_LETTER = "DEAD_LETTER"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=64)
    external_event_id = models.CharField(max_length=128)
    tenant_id = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    encrypted_payload = models.BinaryField(null=True, blank=True)
    payload_reference = models.CharField(max_length=255, blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)
    signature_timestamp = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_owner = models.CharField(max_length=128, blank=True, default="")
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=64, blank=True, default="")
    request_id = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        db_table = "financial_provider_webhook_inbox"
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "external_event_id"),
                name="financial_provider_webhook_unique",
            )
        ]
        indexes = [
            models.Index(fields=("status", "next_attempt_at"), name="fin_webhook_ready_idx"),
            models.Index(fields=("tenant_id", "received_at"), name="fin_webhook_tenant_idx"),
        ]


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


class Destination(models.Model):
    class Type(models.TextChoices):
        CRYPTO = "CRYPTO"
        FIAT = "FIAT"

    class Status(models.TextChoices):
        PENDING = "PENDING"
        VERIFIED = "VERIFIED"
        LOCKED = "LOCKED"
        REVOKED = "REVOKED"

    destination_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.UUIDField()
    account_ref = models.UUIDField()
    owner_ref = models.PositiveBigIntegerField()
    type = models.CharField(max_length=12, choices=Type.choices)
    asset = models.CharField(max_length=12)
    network = models.CharField(max_length=32)
    masked_display = models.CharField(max_length=96)
    destination_fingerprint = models.CharField(max_length=64)
    beneficiary_ref = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    cooldown_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "financial_destinations"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_ref", "account_ref", "type", "network", "destination_fingerprint"],
                name="financial_destination_scope_unique",
            )
        ]
        indexes = [
            models.Index(fields=["tenant_ref", "owner_ref", "status"], name="financial_dest_owner_idx"),
        ]


class FinancialHaltRequest(ImmutableFinancialRecord):
    class State(models.TextChoices):
        ACTIVE = "ACTIVE"
        READ_ONLY = "READ_ONLY"
        WITHDRAWALS_HALTED = "WITHDRAWALS_HALTED"
        FUNDING_HALTED = "FUNDING_HALTED"
        ALL_MUTATIONS_HALTED = "ALL_MUTATIONS_HALTED"

    request_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.UUIDField()
    proposed_state = models.CharField(max_length=24, choices=State.choices)
    requested_by = models.PositiveBigIntegerField()
    reason_code = models.CharField(max_length=64)
    policy_version = models.CharField(max_length=32)
    correlation_id = models.UUIDField()
    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "financial_halt_requests"
        indexes = [models.Index(fields=["tenant_ref", "requested_at"], name="financial_halt_req_tenant_idx")]


class FinancialHaltApproval(ImmutableFinancialRecord):
    approval_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.OneToOneField(
        FinancialHaltRequest, on_delete=models.PROTECT, related_name="approval",
    )
    approved_by = models.PositiveBigIntegerField()
    correlation_id = models.UUIDField()
    approved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "financial_halt_approvals"
        indexes = [models.Index(fields=["approved_at"], name="financial_halt_approved_idx")]


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
