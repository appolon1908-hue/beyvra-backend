import hashlib
import secrets
import uuid

from django.conf import settings
from django.db import models


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OrganizationMembership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=32, default="member")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "organization"), name="unique_org_membership")]


class ExternalIdentity(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="external_identities")
    external_user_id = models.CharField(max_length=255)
    source = models.CharField(max_length=80, default="third_party_crm")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "external_user_id"), name="unique_external_identity")]


class ServiceToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="service_tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    environment = models.CharField(max_length=32, default="staging")
    fingerprint = models.CharField(max_length=16, default="")
    last_four = models.CharField(max_length=4, default="")
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="issued_service_tokens")

    @classmethod
    def issue(cls, organization, name, scopes):
        from .crypto import fingerprint, token_digest
        raw = "cs_" + secrets.token_urlsafe(32)
        return cls.objects.create(organization=organization, name=name, scopes=scopes,
                                  token_hash=token_digest(raw), fingerprint=fingerprint(raw), last_four=raw[-4:],
                                  environment=getattr(settings, "API_ENV", "staging")), raw


class DemoAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="demo_accounts")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="demo_accounts")
    account_type = models.CharField(max_length=8, default="DEMO", editable=False)
    currency = models.CharField(max_length=3, default="USD", editable=False)
    withdrawable = models.BooleanField(default=False, editable=False)
    transferable = models.BooleanField(default=False, editable=False)
    real_money = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "organization"), name="one_demo_account_per_user_org")]


class DemoLedgerEntry(models.Model):
    ENTRY_TYPE = "DEMO_INITIAL_CREDIT"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(DemoAccount, on_delete=models.CASCADE, related_name="ledger_entries")
    entry_type = models.CharField(max_length=40, default=ENTRY_TYPE, editable=False)
    amount_cents = models.PositiveIntegerField(default=200000, editable=False)
    currency = models.CharField(max_length=3, default="USD", editable=False)
    reference = models.CharField(max_length=255, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("account", "entry_type"), name="one_demo_initial_credit")]


class CRMConnection(models.Model):
    PROVIDERS = (("generic_webhook", "Generic HTTPS webhook"), ("odoo", "Odoo adapter"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="crm_connections")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="crm_connections")
    name = models.CharField(max_length=120)
    provider = models.CharField(max_length=32, choices=PROVIDERS, default="generic_webhook")
    endpoint = models.URLField(max_length=500)
    # Deprecated compatibility column; values are nulled after encryption migration.
    secret_encrypted = models.TextField(null=True, blank=True)
    secret_ciphertext = models.TextField(null=True, blank=True)
    secret_nonce = models.CharField(max_length=64, null=True, blank=True)
    secret_key_version = models.CharField(max_length=32, default="v1")
    secret_fingerprint = models.CharField(max_length=16, default="")
    secret_created_at = models.DateTimeField(null=True, blank=True)
    secret_rotated_at = models.DateTimeField(null=True, blank=True)
    secret_revoked_at = models.DateTimeField(null=True, blank=True)
    field_mapping = models.JSONField(default=dict, blank=True)
    event_categories = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class UserImport(models.Model):
    STATUS = (("UPLOADED", "Uploaded"), ("COMMITTED", "Committed"), ("PROCESSING", "Processing"), ("COMPLETED", "Completed"), ("CANCELLED", "Cancelled"), ("FAILED", "Failed"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="user_imports")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, choices=STATUS, default="UPLOADED")
    file_name = models.CharField(max_length=255)
    row_count = models.PositiveIntegerField(default=0)
    valid_count = models.PositiveIntegerField(default=0)
    invalid_count = models.PositiveIntegerField(default=0)
    idempotency_key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "idempotency_key"), name="unique_import_idempotency")]


class UserImportRow(models.Model):
    import_job = models.ForeignKey(UserImport, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    data = models.JSONField(default=dict)
    errors = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, default="VALID")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("import_job", "row_number"), name="unique_import_row")]


class IntegrationAuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    correlation_id = models.UUIDField(default=uuid.uuid4)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
