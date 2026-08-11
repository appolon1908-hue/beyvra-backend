import uuid
from django.db import models


class ProcessedEvent(models.Model):
    event_id = models.UUIDField(primary_key=True)
    event_type = models.CharField(max_length=128)
    tenant_ref = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "financial_inbox"


class DeadLetterEvent(models.Model):
    event_id = models.UUIDField(primary_key=True)
    failure_type = models.CharField(max_length=64)
    retry_count = models.PositiveIntegerField(default=0)
    first_failed_at = models.DateTimeField(auto_now_add=True)
    last_failed_at = models.DateTimeField(auto_now=True)
    safe_error_reference = models.CharField(max_length=128)

    class Meta:
        db_table = "financial_dead_letters"


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
