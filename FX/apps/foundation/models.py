import uuid

from django.db import models


class OutboxEvent(models.Model):
    class State(models.TextChoices):
        PENDING = "PENDING"
        CLAIMED = "CLAIMED"
        PUBLISHED = "PUBLISHED"
        DEAD_LETTER = "DEAD_LETTER"

    id = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    aggregate_type = models.CharField(max_length=64)
    aggregate_id = models.CharField(max_length=128)
    event_type = models.CharField(max_length=128)
    schema_version = models.PositiveSmallIntegerField(default=1)
    payload = models.JSONField(default=dict)
    correlation_id = models.UUIDField()
    causation_id = models.UUIDField(null=True, blank=True)
    tenant_ref = models.CharField(max_length=128)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=128, blank=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING)
    claimed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("state", "next_attempt_at", "id"), name="outbox_pending_idx")]


class ProcessedEvent(models.Model):
    event_id = models.UUIDField()
    consumer_name = models.CharField(max_length=128)
    payload_hash = models.CharField(max_length=64)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("event_id", "consumer_name"), name="processed_event_consumer_unique")]


class RealtimeChannelEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant_ref = models.CharField(max_length=128)
    channel = models.CharField(max_length=200)
    sequence = models.PositiveBigIntegerField()
    event_id = models.CharField(max_length=128)
    event_type = models.CharField(max_length=128)
    source = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    payload_hash = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()
    server_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("tenant_ref", "channel", "sequence"), name="rt_channel_sequence_unique"),
            models.UniqueConstraint(fields=("tenant_ref", "channel", "payload_hash"), name="rt_channel_payload_unique"),
        ]
        indexes = [
            models.Index(fields=("tenant_ref", "channel", "-sequence"), name="rt_channel_latest_idx"),
            models.Index(fields=("tenant_ref", "channel", "sequence"), name="rt_channel_resume_idx"),
        ]


class IdempotencyRecord(models.Model):
    key = models.CharField(max_length=255)
    tenant_ref = models.CharField(max_length=128)
    actor_ref = models.CharField(max_length=128)
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=16)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField(null=True)
    response_body = models.JSONField(null=True)
    resource_type = models.CharField(max_length=64, blank=True)
    resource_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("key", "tenant_ref", "actor_ref", "endpoint", "method"), name="idempotency_scope_unique")]


class ApplicationAuditEvent(models.Model):
    event_id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    actor_ref = models.CharField(max_length=128)
    action = models.CharField(max_length=128)
    resource_type = models.CharField(max_length=64)
    resource_id = models.CharField(max_length=128)
    before_hash = models.CharField(max_length=64, blank=True)
    after_hash = models.CharField(max_length=64, blank=True)
    request_id = models.CharField(max_length=128)
    correlation_id = models.UUIDField()
    context = models.JSONField(default=dict)
    reason = models.CharField(max_length=255)
    occurred_at = models.DateTimeField()

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("AUDIT_EVENT_APPEND_ONLY")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AUDIT_EVENT_APPEND_ONLY")


class TradingControl(models.Model):
    class State(models.TextChoices):
        ACTIVE = "ACTIVE"
        CLOSE_ONLY = "CLOSE_ONLY"
        CANCEL_ONLY = "CANCEL_ONLY"
        HALTED = "HALTED"
        MAINTENANCE = "MAINTENANCE"

    class Scope(models.TextChoices):
        PLATFORM = "PLATFORM"
        ASSET_CLASS = "ASSET_CLASS"
        INSTRUMENT = "INSTRUMENT"
        ACCOUNT = "ACCOUNT"
        PROVIDER = "PROVIDER"

    scope = models.CharField(max_length=16, choices=Scope.choices)
    scope_ref = models.CharField(max_length=128, default="*")
    state = models.CharField(max_length=16, choices=State.choices)
    reason = models.CharField(max_length=255)
    request_id = models.CharField(max_length=128)
    changed_by_ref = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("scope", "scope_ref"), name="trading_control_scope_unique")]
