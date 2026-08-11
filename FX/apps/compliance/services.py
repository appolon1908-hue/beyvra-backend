from django.db import transaction
from django.utils import timezone
from .domain import AccountState, AmlState, EligibilityDecisionValue, EligibilityResult, JurisdictionState, KYC_TRANSITIONS, KycState, RestrictionType, SanctionsState
from .models import AccountRestriction, ComplianceAuditEvent, ComplianceCase, ComplianceCaseEvent, ComplianceOverride, ComplianceProfile, EligibilityDecision
from .metrics import eligibility_decisions_total
from apps.foundation.services import enqueue_event

POLICY_VERSION = "compliance-2026-08-11.v1"

def _enqueue(profile,event_type,data):
    return enqueue_event(aggregate_type="compliance_profile",aggregate_id=profile.pk,event_type=event_type,tenant_ref=profile.organization_id,payload={"channel":f"{event_type}.{profile.user_id}","data":data})


def _active_restrictions(profile, now):
    return list(profile.restrictions.filter(active=True).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)).values_list("restriction_type", flat=True))


from django.db import models


def _evaluate(profile, capability, *, persist=True, context_ref=""):
    now = timezone.now(); reasons = []
    review = False
    if profile.account_state == AccountState.PENDING: reasons.append("ACCOUNT_RESTRICTED")
    elif profile.account_state == AccountState.RESTRICTED: reasons.append("ACCOUNT_RESTRICTED")
    elif profile.account_state == AccountState.SUSPENDED: reasons.append("ACCOUNT_SUSPENDED")
    elif profile.account_state == AccountState.CLOSED: reasons.append("ACCOUNT_RESTRICTED")
    if profile.kyc_state == KycState.NOT_STARTED: reasons.append("KYC_REQUIRED")
    elif profile.kyc_state in (KycState.PENDING, KycState.IN_REVIEW): reasons.append("KYC_PENDING")
    elif profile.kyc_state == KycState.REJECTED: reasons.append("KYC_REJECTED")
    elif profile.kyc_state in (KycState.EXPIRED, KycState.REQUIRES_UPDATE): reasons.append("KYC_REQUIRED")
    if profile.kyc_expires_at and profile.kyc_expires_at <= now: reasons.append("KYC_REQUIRED")
    if profile.kyc_next_review_at and profile.kyc_next_review_at <= now: reasons.append("KYC_REQUIRED")
    if profile.aml_state in (AmlState.NOT_SCREENED, AmlState.PENDING, AmlState.REVIEW_REQUIRED): reasons.append("AML_REVIEW"); review = True
    elif profile.aml_state == AmlState.BLOCKED: reasons.append("AML_BLOCKED")
    if profile.aml_next_review_at and profile.aml_next_review_at <= now: reasons.append("AML_REVIEW"); review = True
    if profile.sanctions_state in (SanctionsState.NOT_CHECKED, SanctionsState.POSSIBLE_MATCH, SanctionsState.MANUAL_REVIEW): reasons.append("SANCTIONS_REVIEW"); review = True
    elif profile.sanctions_state == SanctionsState.CONFIRMED_MATCH: reasons.append("SANCTIONS_BLOCKED")
    if profile.jurisdiction_state == JurisdictionState.UNKNOWN: reasons.append("JURISDICTION_RESTRICTED"); review = True
    elif profile.jurisdiction_state in (JurisdictionState.RESTRICTED, JurisdictionState.LIMITED): reasons.append("JURISDICTION_RESTRICTED")
    if profile.jurisdiction_next_review_at and profile.jurisdiction_next_review_at <= now: reasons.append("JURISDICTION_RESTRICTED"); review = True
    blocking = {"TRADING": RestrictionType.TRADING_DISABLED, "DEPOSIT": RestrictionType.DEPOSITS_DISABLED, "WITHDRAWAL": RestrictionType.WITHDRAWALS_DISABLED, "TRANSFER": RestrictionType.TRANSFERS_DISABLED}[capability]
    for restriction in _active_restrictions(profile, now):
        if restriction == RestrictionType.MANUAL_REVIEW_REQUIRED: reasons.append("MANUAL_REVIEW_REQUIRED"); review = True
        elif restriction in (blocking, RestrictionType.ACCOUNT_READ_ONLY): reasons.append("TRADING_DISABLED" if capability == "TRADING" else f"{capability}S_DISABLED")
    reasons = tuple(dict.fromkeys(reasons))
    if not reasons: result = EligibilityResult.ALLOWED
    elif review and not any(x in reasons for x in ("AML_BLOCKED","SANCTIONS_BLOCKED","ACCOUNT_SUSPENDED","KYC_REJECTED")): result = EligibilityResult.REVIEW_REQUIRED
    else: result = EligibilityResult.DENIED
    value = EligibilityDecisionValue(result, reasons, POLICY_VERSION, now)
    eligibility_decisions_total.labels(capability=capability,result=result,reason=reasons[0] if reasons else "NONE").inc()
    if persist:
        EligibilityDecision.objects.create(account=profile, capability=capability, result=result, reason_codes=list(reasons), policy_version=POLICY_VERSION, evaluated_at=now, context_ref=context_ref)
        ComplianceAuditEvent.objects.create(account=profile, event_type="ELIGIBILITY_DECISION", reason_codes=list(reasons), state_after={"capability": capability, "result": result}, policy_version=POLICY_VERSION)
    return value


def get_trading_eligibility(account, **kwargs): return _evaluate(account, "TRADING", **kwargs)
def get_deposit_eligibility(account, **kwargs): return _evaluate(account, "DEPOSIT", **kwargs)
def get_withdrawal_eligibility(account, **kwargs): return _evaluate(account, "WITHDRAWAL", **kwargs)
def get_transfer_eligibility(account, **kwargs): return _evaluate(account, "TRANSFER", **kwargs)


@transaction.atomic
def transition_kyc(account_id, new_state, *, actor_ref="SYSTEM", evidence_ref=""):
    profile = ComplianceProfile.objects.select_for_update().get(pk=account_id)
    old = KycState(profile.kyc_state); new = KycState(new_state)
    if new not in KYC_TRANSITIONS[old]: raise ValueError("INVALID_KYC_TRANSITION")
    if new == KycState.APPROVED and not evidence_ref: raise ValueError("VERIFIED_EVIDENCE_REQUIRED")
    before = {"kyc_state": old}; profile.kyc_state = new; profile.provider_reference = evidence_ref or profile.provider_reference; profile.version += 1; profile.save()
    ComplianceAuditEvent.objects.create(account=profile, event_type="KYC_STATE_CHANGED", actor_ref=actor_ref, state_before=before, state_after={"kyc_state": new})
    _enqueue(profile,"compliance.profile.updated.v1",{"kyc_state":new,"version":profile.version})
    return profile


@transaction.atomic
def add_restriction(profile, restriction_type, reason_code, source, actor):
    profile = ComplianceProfile.objects.select_for_update().get(pk=profile.pk)
    restriction = AccountRestriction.objects.create(account=profile, restriction_type=restriction_type, reason_code=reason_code, source=source, created_by=actor)
    ComplianceAuditEvent.objects.create(account=profile, event_type="RESTRICTION_ADDED", actor_ref=str(actor.pk), reason_codes=[reason_code], state_after={"restriction_type": restriction_type})
    _enqueue(profile,"compliance.restriction.updated.v1",{"restriction_type":restriction_type,"active":True,"version":profile.version})
    return restriction

@transaction.atomic
def update_account_state(account_id,new_state,actor_ref="SYSTEM",reason_codes=None):
    profile=ComplianceProfile.objects.select_for_update().get(pk=account_id); new=AccountState(new_state); old=profile.account_state
    allowed={AccountState.PENDING:{AccountState.ACTIVE,AccountState.RESTRICTED,AccountState.SUSPENDED,AccountState.CLOSED},AccountState.ACTIVE:{AccountState.RESTRICTED,AccountState.SUSPENDED,AccountState.CLOSED},AccountState.RESTRICTED:{AccountState.ACTIVE,AccountState.SUSPENDED,AccountState.CLOSED},AccountState.SUSPENDED:{AccountState.RESTRICTED,AccountState.CLOSED},AccountState.CLOSED:set()}
    if new not in allowed[AccountState(old)]:raise ValueError("INVALID_ACCOUNT_TRANSITION")
    profile.account_state=new; profile.version+=1; profile.save()
    ComplianceAuditEvent.objects.create(account=profile,event_type="ACCOUNT_STATE_CHANGED",actor_ref=actor_ref,reason_codes=reason_codes or [],state_before={"account_state":old},state_after={"account_state":new})
    _enqueue(profile,"compliance.profile.updated.v1",{"account_state":new,"version":profile.version})
    return profile

@transaction.atomic
def create_case(profile, case_type, priority, reason_codes, actor):
    case = ComplianceCase.objects.create(account=profile, case_type=case_type, priority=priority, reason_codes=reason_codes)
    ComplianceCaseEvent.objects.create(case=case,event_type="CASE_CREATED",actor=actor,metadata={"reason_codes":reason_codes})
    ComplianceAuditEvent.objects.create(account=profile,event_type="CASE_CREATED",actor_ref=str(actor.pk),reason_codes=reason_codes,state_after={"case_id":str(case.pk),"status":"OPEN"})
    return case

@transaction.atomic
def append_case_event(case_id, event_type, actor, metadata=None):
    case=ComplianceCase.objects.select_for_update().get(pk=case_id)
    transitions={"CASE_ASSIGNED":"IN_REVIEW","CASE_ESCALATED":"ESCALATED","CASE_APPROVED":"RESOLVED_APPROVED","CASE_REJECTED":"RESOLVED_REJECTED","CASE_CLOSED":"CLOSED"}
    allowed={"CASE_ASSIGNED","CASE_NOTE_ADDED","CASE_ESCALATED","CASE_APPROVED","CASE_REJECTED","CASE_CLOSED"}
    if event_type not in allowed: raise ValueError("INVALID_CASE_EVENT")
    if case.status in ("RESOLVED_APPROVED","RESOLVED_REJECTED","CLOSED") and event_type != "CASE_CLOSED": raise ValueError("CASE_TERMINAL")
    event=ComplianceCaseEvent.objects.create(case=case,event_type=event_type,actor=actor,metadata=metadata or {})
    if event_type in transitions:
        case.status=transitions[event_type]
        if event_type in ("CASE_APPROVED","CASE_REJECTED"): case.resolved_at=timezone.now(); case.resolution=transitions[event_type]
        case.save()
        ComplianceAuditEvent.objects.create(account=case.account,event_type="CASE_RESOLUTION" if event_type in ("CASE_APPROVED","CASE_REJECTED") else event_type,actor_ref=str(actor.pk),reason_codes=case.reason_codes,state_after={"case_id":str(case.pk),"status":case.status})
    return event

@transaction.atomic
def request_override(profile, control, new_state, reason, requester, expires_at=None):
    current={"KYC_STATE":profile.kyc_state,"AML_STATE":profile.aml_state,"SANCTIONS_STATE":profile.sanctions_state}.get(control)
    if control.startswith("REMOVE_RESTRICTION:"):
        restriction_id=control.split(":",1)[1]
        restriction=profile.restrictions.filter(pk=restriction_id,active=True).first()
        if not restriction: raise ValueError("RESTRICTION_NOT_FOUND")
        current="ACTIVE"; new_state="INACTIVE"
    elif current is None: raise ValueError("INVALID_OVERRIDE_CONTROL")
    else:
        valid={"KYC_STATE":KycState,"AML_STATE":AmlState,"SANCTIONS_STATE":SanctionsState}[control]
        try:new_state=valid(new_state).value
        except ValueError:raise ValueError("INVALID_OVERRIDE_STATE")
    override=ComplianceOverride.objects.create(account=profile,control=control,previous_state=current,new_state=new_state,reason=reason,requested_by=requester,expires_at=expires_at)
    ComplianceAuditEvent.objects.create(account=profile,event_type="OVERRIDE_REQUESTED",actor_ref=str(requester.pk),state_before={"control":control,"state":current},state_after={"requested_state":new_state})
    return override

@transaction.atomic
def approve_override(override_id, checker):
    override=ComplianceOverride.objects.select_for_update().select_related("account").get(pk=override_id)
    if override.approved_at: return override
    if override.requested_by_id == checker.pk: raise ValueError("MAKER_CHECKER_REQUIRED")
    if override.expires_at and override.expires_at <= timezone.now(): raise ValueError("OVERRIDE_EXPIRED")
    profile=ComplianceProfile.objects.select_for_update().get(pk=override.account_id)
    if override.control.startswith("REMOVE_RESTRICTION:"):
        restriction=AccountRestriction.objects.select_for_update().get(pk=override.control.split(":",1)[1],account=profile,active=True)
        restriction.active=False; restriction.save(update_fields=["active"])
        event_type="RESTRICTION_REMOVED"
    else:
        field={"KYC_STATE":"kyc_state","AML_STATE":"aml_state","SANCTIONS_STATE":"sanctions_state"}.get(override.control)
        if not field or getattr(profile,field) != override.previous_state: raise ValueError("OVERRIDE_STALE")
        setattr(profile,field,override.new_state); profile.version+=1; profile.save()
        event_type="MANUAL_OVERRIDE"
    override.approved_by=checker; override.approved_at=timezone.now(); override.full_clean(); override.save(update_fields=["approved_by","approved_at"])
    ComplianceAuditEvent.objects.create(account=profile,event_type=event_type,actor_ref=str(checker.pk),state_before={"control":override.control,"state":override.previous_state},state_after={"state":override.new_state,"override_id":str(override.pk)})
    if event_type=="RESTRICTION_REMOVED":_enqueue(profile,"compliance.restriction.updated.v1",{"restriction_id":override.control.split(":",1)[1],"active":False,"version":profile.version})
    else:_enqueue(profile,"compliance.profile.updated.v1",{"version":profile.version})
    return override
