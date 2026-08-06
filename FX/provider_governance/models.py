from django.db import models


class GovernanceStatus(models.TextChoices):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"
    EXPIRED = "EXPIRED"


class ProviderDefinition(models.Model):
    provider_id = models.CharField(max_length=64, unique=True)
    provider_type = models.CharField(max_length=32)
    enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "provider_governance_providers"


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
    environment = models.CharField(max_length=16)
    status = models.CharField(max_length=16, choices=GovernanceStatus.choices, default=GovernanceStatus.PENDING)
    approved_by = models.CharField(max_length=255, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    approval_reference = models.CharField(max_length=255, unique=True)
    license_reference = models.CharField(max_length=255)
    credential_reference = models.CharField(max_length=255)
    allowed_products = models.JSONField(default=list)
    allowed_symbols = models.JSONField(default=list)
    allowed_regions = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "provider_governance_provider_approvals"
        indexes = [models.Index(fields=["provider", "environment", "status"])]


class ProviderGovernanceAudit(models.Model):
    provider = models.ForeignKey(ProviderDefinition, null=True, on_delete=models.SET_NULL)
    decision = models.CharField(max_length=16)
    reason_code = models.CharField(max_length=64)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "provider_governance_audit"
        ordering = ["-occurred_at"]
