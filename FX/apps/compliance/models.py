import uuid
from django.conf import settings
from django.db import models, transaction
from integrations.models import Organization
from .domain import AccountState, AmlState, JurisdictionState, KycState, ProviderGovernanceState, ReasonCode, RequirementType, RestrictionType, SanctionsState


def choices(enum): return [(item.value, item.value) for item in enum]


class ComplianceProfile(models.Model):
    account_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="compliance_profiles")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compliance_profiles")
    account_state = models.CharField(max_length=16, choices=choices(AccountState), default=AccountState.PENDING)
    kyc_state = models.CharField(max_length=20, choices=choices(KycState), default=KycState.NOT_STARTED)
    aml_state = models.CharField(max_length=20, choices=choices(AmlState), default=AmlState.NOT_SCREENED)
    sanctions_state = models.CharField(max_length=20, choices=choices(SanctionsState), default=SanctionsState.NOT_CHECKED)
    jurisdiction_state = models.CharField(max_length=16, choices=choices(JurisdictionState), default=JurisdictionState.UNKNOWN)
    jurisdiction_evidence_ref = models.CharField(max_length=255, blank=True, default="")
    kyc_evidence_ref = models.CharField(max_length=255, blank=True, default="")
    aml_evidence_ref = models.CharField(max_length=255, blank=True, default="")
    sanctions_evidence_ref = models.CharField(max_length=255, blank=True, default="")
    kyc_expires_at = models.DateTimeField(null=True, blank=True)
    kyc_next_review_at = models.DateTimeField(null=True, blank=True)
    aml_next_review_at = models.DateTimeField(null=True, blank=True)
    jurisdiction_next_review_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("organization", "user"), name="unique_compliance_profile_org_user"),
            models.CheckConstraint(condition=models.Q(account_state__in=[x.value for x in AccountState]),name="valid_compliance_account_state"),
            models.CheckConstraint(condition=models.Q(kyc_state__in=[x.value for x in KycState]),name="valid_compliance_kyc_state"),
            models.CheckConstraint(condition=models.Q(aml_state__in=[x.value for x in AmlState]),name="valid_compliance_aml_state"),
            models.CheckConstraint(condition=models.Q(sanctions_state__in=[x.value for x in SanctionsState]),name="valid_compliance_sanctions_state"),
            models.CheckConstraint(condition=models.Q(jurisdiction_state__in=[x.value for x in JurisdictionState]),name="valid_compliance_jurisdiction_state"),
        ]
    def delete(self, *args, **kwargs): raise ValueError("COMPLIANCE_RETENTION_REVIEW_REQUIRED")


class AccountRestriction(models.Model):
    restriction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(ComplianceProfile, on_delete=models.CASCADE, related_name="restrictions")
    restriction_type = models.CharField(max_length=32, choices=choices(RestrictionType))
    reason_code = models.CharField(max_length=64, choices=choices(ReasonCode))
    source = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="compliance_restrictions_created")
    active = models.BooleanField(default=True)
    class Meta:
        indexes = [models.Index(fields=("account", "active", "restriction_type"), name="restriction_active_idx")]
        constraints = [models.CheckConstraint(condition=models.Q(restriction_type__in=[x.value for x in RestrictionType]),name="valid_compliance_restriction_type"),models.CheckConstraint(condition=models.Q(reason_code__in=[x.value for x in ReasonCode]),name="valid_compliance_restriction_reason")]


class ComplianceRequirement(models.Model):
    requirement_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(ComplianceProfile, on_delete=models.CASCADE, related_name="requirements")
    type = models.CharField(max_length=40, choices=choices(RequirementType))
    status = models.CharField(max_length=20, default="OPEN", choices=[(x,x) for x in ("OPEN","PENDING","COMPLETED","WAIVED","EXPIRED")])
    required = models.BooleanField(default=True)
    deadline = models.DateTimeField(null=True, blank=True)
    user_action = models.CharField(max_length=160, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: constraints=[models.CheckConstraint(condition=models.Q(type__in=[x.value for x in RequirementType]),name="valid_compliance_requirement_type"),models.CheckConstraint(condition=models.Q(status__in=("OPEN","PENDING","COMPLETED","WAIVED","EXPIRED")),name="valid_compliance_requirement_status")]
    def save(self, *args, **kwargs):
        with transaction.atomic():
            result=super().save(*args,**kwargs)
            from .services import _enqueue
            _enqueue(self.account,"compliance.requirement.updated.v1",{"requirement_id":str(self.pk),"type":self.type,"status":self.status,"required":self.required})
            return result


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
    class Meta: constraints=[models.CheckConstraint(condition=models.Q(status__in=("OPEN","IN_REVIEW","ESCALATED","RESOLVED_APPROVED","RESOLVED_REJECTED","CLOSED")),name="valid_compliance_case_status")]


class ComplianceCaseEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(ComplianceCase, on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=32, choices=[(x,x) for x in ("CASE_CREATED","CASE_ASSIGNED","CASE_NOTE_ADDED","CASE_ESCALATED","CASE_APPROVED","CASE_REJECTED","CASE_CLOSED")])
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: constraints=[models.CheckConstraint(condition=models.Q(event_type__in=("CASE_CREATED","CASE_ASSIGNED","CASE_NOTE_ADDED","CASE_ESCALATED","CASE_APPROVED","CASE_REJECTED","CASE_CLOSED")),name="valid_compliance_case_event")]
    def save(self, *args, **kwargs):
        if self.pk and ComplianceCaseEvent.objects.filter(pk=self.pk).exists(): raise ValueError("CASE_EVENTS_ARE_IMMUTABLE")
        return super().save(*args, **kwargs)
    def delete(self, *args, **kwargs): raise ValueError("CASE_EVENTS_ARE_IMMUTABLE")


class ComplianceOverride(models.Model):
    override_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(ComplianceProfile, on_delete=models.PROTECT, related_name="overrides")
    control = models.CharField(max_length=80); previous_state = models.CharField(max_length=64); new_state = models.CharField(max_length=64)
    reason = models.CharField(max_length=255); evidence_ref = models.CharField(max_length=255, blank=True, default=""); requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compliance_overrides_requested")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="compliance_overrides_approved")
    requested_at = models.DateTimeField(auto_now_add=True); approved_at = models.DateTimeField(null=True, blank=True); expires_at = models.DateTimeField(null=True, blank=True)
    class Meta: constraints=[models.CheckConstraint(condition=models.Q(approved_by__isnull=True)|~models.Q(approved_by=models.F("requested_by")),name="override_independent_checker"),models.CheckConstraint(condition=(models.Q(approved_by__isnull=True,approved_at__isnull=True)|models.Q(approved_by__isnull=False,approved_at__isnull=False)),name="override_approval_complete"),models.CheckConstraint(condition=~(models.Q(control="KYC_STATE",new_state="APPROVED")|models.Q(control="AML_STATE",new_state="CLEARED")|models.Q(control="SANCTIONS_STATE",new_state="CLEAR"))|~models.Q(evidence_ref=""),name="override_clearance_has_evidence")]
    def clean(self):
        if self.approved_by_id and self.approved_by_id == self.requested_by_id: from django.core.exceptions import ValidationError; raise ValidationError("MAKER_CHECKER_REQUIRED")
    def delete(self, *args, **kwargs): raise ValueError("COMPLIANCE_OVERRIDES_ARE_APPEND_ONLY")


class EligibilityDecision(models.Model):
    decision_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(ComplianceProfile, on_delete=models.PROTECT, related_name="eligibility_decisions")
    capability = models.CharField(max_length=16); result = models.CharField(max_length=20); reason_codes = models.JSONField(default=list)
    policy_version = models.CharField(max_length=32); evaluated_at = models.DateTimeField(); context_ref = models.CharField(max_length=128, blank=True, default="")
    class Meta: constraints=[models.CheckConstraint(condition=models.Q(capability__in=("TRADING","DEPOSIT","WITHDRAWAL","TRANSFER")),name="valid_eligibility_capability"),models.CheckConstraint(condition=models.Q(result__in=("ALLOWED","DENIED","REVIEW_REQUIRED")),name="valid_eligibility_result")]
    def save(self, *args, **kwargs):
        if self.pk and EligibilityDecision.objects.filter(pk=self.pk).exists(): raise ValueError("ELIGIBILITY_DECISIONS_ARE_IMMUTABLE")
        return super().save(*args, **kwargs)
    def delete(self, *args, **kwargs): raise ValueError("ELIGIBILITY_DECISIONS_ARE_IMMUTABLE")


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


class ComplianceInboxEvent(models.Model):
    provider = models.CharField(max_length=64); provider_event_id = models.CharField(max_length=255); payload_hash = models.CharField(max_length=64); received_at = models.DateTimeField(auto_now_add=True); processed_at = models.DateTimeField(null=True, blank=True)
    class Meta: constraints = [models.UniqueConstraint(fields=("provider", "provider_event_id"), name="unique_compliance_provider_event")]


class ComplianceProviderGovernance(models.Model):
    provider_key = models.CharField(max_length=64, unique=True); state = models.CharField(max_length=32, choices=choices(ProviderGovernanceState), default=ProviderGovernanceState.DISABLED); capabilities = models.JSONField(default=list); updated_at = models.DateTimeField(auto_now=True)
    class Meta: constraints=[models.CheckConstraint(condition=models.Q(state__in=[x.value for x in ProviderGovernanceState]),name="valid_compliance_provider_state")]
