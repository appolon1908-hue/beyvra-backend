import uuid
from django.conf import settings
from django.db import models
from integrations.models import Organization
from .domain import AccountState, AmlState, JurisdictionState, KycState, RestrictionType, SanctionsState


def choices(enum): return [(item.value, item.value) for item in enum]


class ComplianceProfile(models.Model):
    account_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="compliance_profiles")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compliance_profiles")
    account_state = models.CharField(max_length=16, choices=choices(AccountState), default=AccountState.PENDING)
    kyc_state = models.CharField(max_length=20, choices=choices(KycState), default=KycState.NOT_STARTED)
    aml_state = models.CharField(max_length=20, choices=choices(AmlState), default=AmlState.NOT_SCREENED)
    sanctions_state = models.CharField(max_length=20, choices=choices(SanctionsState), default=SanctionsState.NOT_CHECKED)
    jurisdiction_state = models.CharField(max_length=16, choices=choices(JurisdictionState), default=JurisdictionState.UNKNOWN)
    jurisdiction_evidence_ref = models.CharField(max_length=255, blank=True, default="")
    provider_reference = models.CharField(max_length=255, blank=True, default="")
    kyc_expires_at = models.DateTimeField(null=True, blank=True)
    kyc_next_review_at = models.DateTimeField(null=True, blank=True)
    aml_next_review_at = models.DateTimeField(null=True, blank=True)
    jurisdiction_next_review_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "user"), name="unique_compliance_profile_org_user")]


class AccountRestriction(models.Model):
    restriction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(ComplianceProfile, on_delete=models.CASCADE, related_name="restrictions")
    restriction_type = models.CharField(max_length=32, choices=choices(RestrictionType))
    reason_code = models.CharField(max_length=64)
    source = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="compliance_restrictions_created")
    active = models.BooleanField(default=True)
    class Meta:
        indexes = [models.Index(fields=("account", "active", "restriction_type"), name="restriction_active_idx")]


class ComplianceRequirement(models.Model):
    requirement_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(ComplianceProfile, on_delete=models.CASCADE, related_name="requirements")
    type = models.CharField(max_length=40)
    status = models.CharField(max_length=20, default="OPEN")
    required = models.BooleanField(default=True)
    deadline = models.DateTimeField(null=True, blank=True)
    user_action = models.CharField(max_length=160, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class ComplianceCase(models.Model):
    case_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(ComplianceProfile, on_delete=models.PROTECT, related_name="cases")
    case_type = models.CharField(max_length=40)
    status = models.CharField(max_length=24, default="OPEN", choices=[(x,x) for x in ("OPEN","IN_REVIEW","ESCALATED","RESOLVED_APPROVED","RESOLVED_REJECTED","CLOSED")])
    priority = models.CharField(max_length=16, default="NORMAL")
    reason_codes = models.JSONField(default=list)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="compliance_cases")
    created_at = models.DateTimeField(auto_now_add=True); updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True); resolution = models.CharField(max_length=64, blank=True, default="")


class ComplianceCaseEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(ComplianceCase, on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=32)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    def save(self, *args, **kwargs):
        if self.pk and ComplianceCaseEvent.objects.filter(pk=self.pk).exists(): raise ValueError("CASE_EVENTS_ARE_IMMUTABLE")
        return super().save(*args, **kwargs)
    def delete(self, *args, **kwargs): raise ValueError("CASE_EVENTS_ARE_IMMUTABLE")


class ComplianceOverride(models.Model):
    override_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(ComplianceProfile, on_delete=models.PROTECT, related_name="overrides")
    control = models.CharField(max_length=40); previous_state = models.CharField(max_length=64); new_state = models.CharField(max_length=64)
    reason = models.CharField(max_length=255); requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compliance_overrides_requested")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="compliance_overrides_approved")
    requested_at = models.DateTimeField(auto_now_add=True); approved_at = models.DateTimeField(null=True, blank=True); expires_at = models.DateTimeField(null=True, blank=True)
    def clean(self):
        if self.approved_by_id and self.approved_by_id == self.requested_by_id: from django.core.exceptions import ValidationError; raise ValidationError("MAKER_CHECKER_REQUIRED")


class EligibilityDecision(models.Model):
    decision_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(ComplianceProfile, on_delete=models.PROTECT, related_name="eligibility_decisions")
    capability = models.CharField(max_length=16); result = models.CharField(max_length=20); reason_codes = models.JSONField(default=list)
    policy_version = models.CharField(max_length=32); evaluated_at = models.DateTimeField(); context_ref = models.CharField(max_length=128, blank=True, default="")


class ComplianceAuditEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(ComplianceProfile, on_delete=models.PROTECT, related_name="audit_events")
    event_type = models.CharField(max_length=40); actor_ref = models.CharField(max_length=128, blank=True, default="SYSTEM")
    reason_codes = models.JSONField(default=list); state_before = models.JSONField(default=dict); state_after = models.JSONField(default=dict)
    policy_version = models.CharField(max_length=32, blank=True, default=""); created_at = models.DateTimeField(auto_now_add=True)
    def save(self, *args, **kwargs):
        if self.pk and ComplianceAuditEvent.objects.filter(pk=self.pk).exists(): raise ValueError("AUDIT_EVENTS_ARE_IMMUTABLE")
        return super().save(*args, **kwargs)
    def delete(self, *args, **kwargs): raise ValueError("AUDIT_EVENTS_ARE_IMMUTABLE")


class ComplianceOutboxEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False); account = models.ForeignKey(ComplianceProfile, on_delete=models.PROTECT)
    event_type = models.CharField(max_length=64); payload = models.JSONField(default=dict); created_at = models.DateTimeField(auto_now_add=True); published_at = models.DateTimeField(null=True, blank=True)


class ComplianceInboxEvent(models.Model):
    provider = models.CharField(max_length=64); provider_event_id = models.CharField(max_length=255); payload_hash = models.CharField(max_length=64); received_at = models.DateTimeField(auto_now_add=True); processed_at = models.DateTimeField(null=True, blank=True)
    class Meta: constraints = [models.UniqueConstraint(fields=("provider", "provider_event_id"), name="unique_compliance_provider_event")]


class ComplianceProviderGovernance(models.Model):
    provider_key = models.CharField(max_length=64, unique=True); state = models.CharField(max_length=32, default="DISABLED"); capabilities = models.JSONField(default=list); updated_at = models.DateTimeField(auto_now=True)
