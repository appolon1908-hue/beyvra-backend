from django.db import models
import uuid
from django.utils import timezone


class GovernanceStatus(models.TextChoices):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"
    EXPIRED = "EXPIRED"


class Environment(models.TextChoices):
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


class CredentialPolicy(models.TextChoices):
    REQUIRED = "REQUIRED"
    NONE = "NONE"


class ProviderDefinition(models.Model):
    provider_id = models.CharField(max_length=64, unique=True)
    provider_type = models.CharField(max_length=32)
    enabled = models.BooleanField(default=False)
    environment = models.CharField(max_length=16, choices=Environment.choices, default=Environment.STAGING)
    license_verified = models.BooleanField(default=False)
    security_approved = models.BooleanField(default=False)
    compliance_approved = models.BooleanField(default=False)
    staging_approved = models.BooleanField(default=False)
    production_approved = models.BooleanField(default=False)
    allowed_asset_classes = models.JSONField(default=list)
    allowed_data_types = models.JSONField(default=list)
    max_staleness_ms = models.PositiveIntegerField(default=0)
    priority = models.PositiveIntegerField(default=100)
    failover_allowed = models.BooleanField(default=False)
    updated_by = models.CharField(max_length=255, default="system")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "provider_governance_providers"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(production_approved=False)
                | (
                    models.Q(enabled=True)
                    & models.Q(license_verified=True)
                    & models.Q(security_approved=True)
                    & models.Q(compliance_approved=True)
                    & models.Q(staging_approved=True)
                ),
                name="provider_production_requires_approvals",
            )
        ]


class ProviderLicense(models.Model):
    provider = models.ForeignKey(ProviderDefinition, on_delete=models.PROTECT, related_name="licenses")
    environment = models.CharField(max_length=16)
    status = models.CharField(max_length=16, choices=GovernanceStatus.choices, default=GovernanceStatus.PENDING)
    license_reference = models.CharField(max_length=255, unique=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "provider_governance_licenses"


class ProviderApproval(models.Model):
    provider = models.ForeignKey(ProviderDefinition, on_delete=models.PROTECT, related_name="approvals")
    provider_type = models.CharField(max_length=32)
    environment = models.CharField(max_length=16, choices=Environment.choices)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=GovernanceStatus.choices, default=GovernanceStatus.PENDING)
    approved_by_principal_id = models.CharField(max_length=255, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    approval_reference = models.CharField(max_length=255, unique=True)
    license = models.ForeignKey(ProviderLicense, null=True, blank=True, on_delete=models.PROTECT, related_name="approvals")
    credential_policy = models.CharField(max_length=16, choices=CredentialPolicy.choices, default=CredentialPolicy.NONE)
    credential_reference = models.CharField(max_length=255, null=True, blank=True)
    allowed_products = models.JSONField(default=list)
    allowed_symbols = models.JSONField(default=list)
    allowed_regions = models.JSONField(default=list)
    supersedes_approval = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="replacement")
    approval_payload_hash = models.CharField(max_length=64, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=255, default="")

    class Meta:
        db_table = "provider_governance_provider_approvals"
        indexes = [models.Index(fields=["provider", "environment", "status"])]
        constraints = [
            models.UniqueConstraint(fields=["provider", "environment", "version"], name="provider_approval_version_unique"),
            models.CheckConstraint(condition=models.Q(environment__in=["STAGING", "PRODUCTION"]), name="provider_approval_environment_valid"),
            models.CheckConstraint(condition=models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=models.F("approved_at")), name="provider_approval_expiry_after_approval"),
            models.CheckConstraint(condition=~models.Q(status="APPROVED") | (models.Q(approved_at__isnull=False) & ~models.Q(approved_by_principal_id="") & models.Q(license__isnull=False)), name="approved_requires_evidence"),
            models.CheckConstraint(condition=(models.Q(credential_policy="NONE", credential_reference__isnull=True) | models.Q(credential_policy="REQUIRED", credential_reference__isnull=False)), name="credential_policy_satisfied"),
        ]


class ProviderGovernanceAudit(models.Model):
    audit_event_id = models.UUIDField(unique=True, editable=False, default=uuid.uuid4)
    provider = models.ForeignKey(ProviderDefinition, null=True, on_delete=models.SET_NULL)
    provider_id_evidence = models.CharField(max_length=64, default="")
    provider_type = models.CharField(max_length=32, default="")
    environment = models.CharField(max_length=16, default="STAGING")
    approval = models.ForeignKey(ProviderApproval, null=True, on_delete=models.SET_NULL)
    approval_version = models.PositiveIntegerField(null=True)
    license = models.ForeignKey(ProviderLicense, null=True, on_delete=models.SET_NULL)
    decision = models.CharField(max_length=16)
    reason_code = models.CharField(max_length=64)
    requested_product = models.CharField(max_length=64, default="")
    requested_symbol = models.CharField(max_length=64, default="")
    requested_region = models.CharField(max_length=64, default="")
    credential_reference_id = models.CharField(max_length=255, blank=True)
    credential_reference_hash = models.CharField(max_length=64, blank=True)
    request_id = models.CharField(max_length=128, blank=True)
    correlation_id = models.CharField(max_length=128, blank=True)
    caller_service = models.CharField(max_length=128, default="unknown")
    resolved_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "provider_governance_audit"
        ordering = ["-resolved_at"]
