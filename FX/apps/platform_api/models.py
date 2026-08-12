import uuid

from django.conf import settings
from django.db import models


class TenantRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("integrations.Organization", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AccountSession(TenantRecord):
    token_jti_hash = models.CharField(max_length=64, unique=True)
    device_label = models.CharField(max_length=120, blank=True)
    last_seen_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)


class AccountSecurityEvent(TenantRecord):
    event_type = models.CharField(max_length=64)
    safe_context = models.JSONField(default=dict, blank=True)


class NotificationPreference(TenantRecord):
    email_enabled = models.BooleanField(default=True)
    in_app_enabled = models.BooleanField(default=True)
    categories = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "user"), name="one_notification_preference_per_tenant_user")]


class SupportCase(TenantRecord):
    subject = models.CharField(max_length=160)
    status = models.CharField(max_length=24, default="OPEN")


class SupportMessage(TenantRecord):
    case = models.ForeignKey(SupportCase, on_delete=models.CASCADE, related_name="messages")
    body = models.TextField(max_length=4000)
    customer_visible = models.BooleanField(default=True, editable=False)


class ReportExport(TenantRecord):
    report_type = models.CharField(max_length=32)
    status = models.CharField(max_length=24, default="PENDING")
    filters = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=255)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "user", "idempotency_key"), name="unique_report_export_idempotency")]


class PrivacyRequest(TenantRecord):
    request_type = models.CharField(max_length=32)
    status = models.CharField(max_length=32, default="PENDING_REVIEW")
    idempotency_key = models.CharField(max_length=255)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "user", "idempotency_key"), name="unique_privacy_request_idempotency")]


class ApiIdempotencyRecord(models.Model):
    organization = models.ForeignKey("integrations.Organization", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    scope = models.CharField(max_length=120)
    key = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "user", "scope", "key"), name="unique_api_idempotency_scope")]


class OperatorAction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("integrations.Organization", on_delete=models.CASCADE)
    action_type = models.CharField(max_length=64)
    target_ref = models.CharField(max_length=255)
    status = models.CharField(max_length=32, default="PENDING_APPROVAL")
    reason = models.CharField(max_length=500)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="operator_actions_requested")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="operator_actions_approved")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)


class PlatformAuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("integrations.Organization", on_delete=models.CASCADE)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=80)
    subject_type = models.CharField(max_length=80)
    subject_ref = models.CharField(max_length=255)
    safe_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("AUDIT_EVENT_IMMUTABLE")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AUDIT_EVENT_IMMUTABLE")


class PlatformOutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("integrations.Organization", on_delete=models.CASCADE)
    event_type = models.CharField(max_length=100)
    aggregate_type = models.CharField(max_length=80)
    aggregate_ref = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)


class WebhookInboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=64)
    purpose = models.CharField(max_length=64)
    provider_event_id = models.CharField(max_length=255)
    payload_hash = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    result = models.CharField(max_length=32, default="RECEIVED")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("provider", "purpose", "provider_event_id"), name="unique_platform_webhook_event")]


class WebhookDeadLetter(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inbox_event = models.OneToOneField(WebhookInboxEvent, on_delete=models.PROTECT, related_name="dead_letter")
    error_code = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
