from django.db import transaction
from django.utils import timezone
import re
from .domain import AccountState, AmlState, EligibilityDecisionValue, EligibilityResult, JurisdictionState, KYC_TRANSITIONS, KycState, ReasonCode, RestrictionType, SanctionsState
from .models import AccountRestriction, ComplianceAuditEvent, ComplianceCase, ComplianceCaseEvent, ComplianceOverride, ComplianceProfile, EligibilityDecision
from .metrics import eligibility_decisions_total
from apps.foundation.services import enqueue_event

POLICY_VERSION = "compliance-2026-08-11.v1"
OPAQUE_REFERENCE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_.-]{0,254}$")

def _validated_evidence_ref(value):
    value=str(value or "")
    if not OPAQUE_REFERENCE.fullmatch(value):raise ValueError("INVALID_EVIDENCE_REFERENCE")
    return value

def effective_profile_states(profile, now=None):
    now = now or timezone.now()
    kyc_state = KycState(profile.kyc_state)
    aml_state = AmlState(profile.aml_state)
    jurisdiction_state = JurisdictionState(profile.jurisdiction_state)
    expired_controls={item.control for item in profile.overrides.all() if item.approved_at and item.expires_at and item.expires_at<=now}
    if "KYC_STATE" in expired_controls and kyc_state==KycState.APPROVED:kyc_state=KycState.REQUIRES_UPDATE
    if "AML_STATE" in expired_controls and aml_state==AmlState.CLEARED:aml_state=AmlState.REVIEW_REQUIRED
    if "SANCTIONS_STATE" in expired_controls and SanctionsState(profile.sanctions_state)==SanctionsState.CLEAR:sanctions_state=SanctionsState.MANUAL_REVIEW
    else:sanctions_state=SanctionsState(profile.sanctions_state)
    if (profile.kyc_expires_at and profile.kyc_expires_at <= now) or (profile.kyc_next_review_at and profile.kyc_next_review_at <= now): kyc_state = KycState.EXPIRED if profile.kyc_expires_at and profile.kyc_expires_at <= now else KycState.REQUIRES_UPDATE
    if profile.aml_next_review_at and profile.aml_next_review_at <= now: aml_state = AmlState.REVIEW_REQUIRED
    if profile.jurisdiction_next_review_at and profile.jurisdiction_next_review_at <= now: jurisdiction_state = JurisdictionState.UNKNOWN
    return {"kyc_state":kyc_state,"aml_state":aml_state,"sanctions_state":sanctions_state,"jurisdiction_state":jurisdiction_state,"account_state":AccountState(profile.account_state)}

def _enqueue(profile,event_type,data):
    return enqueue_event(aggregate_type="compliance_profile",aggregate_id=profile.pk,event_type=event_type,tenant_ref=profile.organization_id,payload={"channel":f"{event_type}.{profile.user_id}","data":data})

def _invalidate_pending_simulation_orders_if_denied(profile):
    decision=_evaluate(profile,"TRADING",persist=False)
    if decision.result==EligibilityResult.ALLOWED:return 0
    from apps.trading.models import TradingOrder
    return TradingOrder.objects.filter(account_ref=str(profile.pk),simulation=True,state="PENDING").update(state="REJECTED",eligibility_policy_version=decision.policy_version,eligibility_result=decision.result,eligibility_reason_codes=list(decision.reason_codes),eligibility_evaluated_at=decision.evaluated_at)


def _active_restrictions(profile, now):
    restrictions=list(profile.restrictions.filter(active=True).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)).values_list("restriction_type", flat=True))
    expired_removals=profile.overrides.filter(approved_at__isnull=False,expires_at__lte=now,control__startswith="REMOVE_RESTRICTION:").values_list("control",flat=True)
    removed_ids=[value.split(":",1)[1] for value in expired_removals]
    restrictions.extend(profile.restrictions.filter(pk__in=removed_ids,active=False).filter(models.Q(expires_at__isnull=True)|models.Q(expires_at__gt=now)).values_list("restriction_type",flat=True))
    return restrictions


from django.db import models


@transaction.atomic
def _evaluate(profile, capability, *, persist=True, context_ref=""):
    now = timezone.now(); reasons = []; states=effective_profile_states(profile,now)
    review = False; deny = False
    if states["account_state"] in (AccountState.PENDING,AccountState.RESTRICTED,AccountState.CLOSED): reasons.append("ACCOUNT_RESTRICTED"); deny=True
    elif states["account_state"] == AccountState.SUSPENDED: reasons.append("ACCOUNT_SUSPENDED"); deny=True
    if states["kyc_state"] == KycState.NOT_STARTED: reasons.append("KYC_REQUIRED"); deny=True
    elif states["kyc_state"] in (KycState.PENDING, KycState.IN_REVIEW): reasons.append("KYC_PENDING"); deny=True
    elif states["kyc_state"] == KycState.REJECTED: reasons.append("KYC_REJECTED"); deny=True
    elif states["kyc_state"] in (KycState.EXPIRED, KycState.REQUIRES_UPDATE): reasons.append("KYC_REQUIRED"); deny=True
    if states["aml_state"] in (AmlState.NOT_SCREENED, AmlState.PENDING, AmlState.REVIEW_REQUIRED): reasons.append("AML_REVIEW"); review = True
    elif states["aml_state"] == AmlState.BLOCKED: reasons.append("AML_BLOCKED"); deny=True
    if states["sanctions_state"] in (SanctionsState.NOT_CHECKED, SanctionsState.POSSIBLE_MATCH, SanctionsState.MANUAL_REVIEW): reasons.append("SANCTIONS_REVIEW"); review = True
    elif states["sanctions_state"] == SanctionsState.CONFIRMED_MATCH: reasons.append("SANCTIONS_BLOCKED"); deny=True
    if states["jurisdiction_state"] == JurisdictionState.UNKNOWN: reasons.append("JURISDICTION_RESTRICTED"); review = True
    elif states["jurisdiction_state"] in (JurisdictionState.RESTRICTED, JurisdictionState.LIMITED): reasons.append("JURISDICTION_RESTRICTED"); deny=True
    blocking = {"TRADING": RestrictionType.TRADING_DISABLED, "DEPOSIT": RestrictionType.DEPOSITS_DISABLED, "WITHDRAWAL": RestrictionType.WITHDRAWALS_DISABLED, "TRANSFER": RestrictionType.TRANSFERS_DISABLED}[capability]
    for restriction in _active_restrictions(profile, now):
        if restriction == RestrictionType.MANUAL_REVIEW_REQUIRED: reasons.append("MANUAL_REVIEW_REQUIRED"); review = True
        elif restriction in (blocking, RestrictionType.ACCOUNT_READ_ONLY): reasons.append("TRADING_DISABLED" if capability == "TRADING" else f"{capability}S_DISABLED"); deny=True
    reasons = tuple(dict.fromkeys(reasons))
    if not reasons: result = EligibilityResult.ALLOWED
    elif deny: result = EligibilityResult.DENIED
    else: result = EligibilityResult.REVIEW_REQUIRED
    value = EligibilityDecisionValue(result, reasons, POLICY_VERSION, now)
    eligibility_decisions_total.labels(capability=capability,result=result,reason=reasons[0] if reasons else "NONE").inc()
    if persist:
        decision=EligibilityDecision.objects.create(account=profile, capability=capability, result=result, reason_codes=list(reasons), policy_version=POLICY_VERSION, evaluated_at=now, context_ref=context_ref)
        ComplianceAuditEvent.objects.create(account=profile, event_type="ELIGIBILITY_DECISION", reason_codes=list(reasons), state_after={"decision_id":str(decision.pk),"capability": capability, "result": result}, policy_version=POLICY_VERSION)
    return value


def _canonical_profile(account):return ComplianceProfile.objects.get(pk=getattr(account,"pk",account))
def get_trading_eligibility(account, **kwargs): return _evaluate(_canonical_profile(account), "TRADING", **kwargs)
def get_deposit_eligibility(account, **kwargs): return _evaluate(_canonical_profile(account), "DEPOSIT", **kwargs)
def get_withdrawal_eligibility(account, **kwargs): return _evaluate(_canonical_profile(account), "WITHDRAWAL", **kwargs)
def get_transfer_eligibility(account, **kwargs): return _evaluate(_canonical_profile(account), "TRANSFER", **kwargs)


@transaction.atomic
def transition_kyc(account_id, new_state, *, actor_ref="SYSTEM", evidence_ref=""):
    profile = ComplianceProfile.objects.select_for_update().get(pk=account_id)
    old = KycState(profile.kyc_state); new = KycState(new_state)
    if new not in KYC_TRANSITIONS[old]: raise ValueError("INVALID_KYC_TRANSITION")
    if new == KycState.APPROVED and not evidence_ref: raise ValueError("VERIFIED_EVIDENCE_REQUIRED")
    if evidence_ref:evidence_ref=_validated_evidence_ref(evidence_ref)
    before = {"kyc_state": old}; profile.kyc_state = new; profile.kyc_evidence_ref = evidence_ref or profile.kyc_evidence_ref; profile.version += 1; profile.save()
    ComplianceAuditEvent.objects.create(account=profile, event_type="KYC_STATE_CHANGED", actor_ref=actor_ref, state_before=before, state_after={"kyc_state": new})
    _enqueue(profile,"compliance.profile.updated.v1",{"kyc_state":new,"version":profile.version})
    _invalidate_pending_simulation_orders_if_denied(profile)
    return profile


@transaction.atomic
def transition_aml(account_id, new_state, *, actor_ref="SYSTEM", evidence_ref=""):
    profile = ComplianceProfile.objects.select_for_update().get(pk=account_id)
    old, new = AmlState(profile.aml_state), AmlState(new_state)
    allowed = {
        AmlState.NOT_SCREENED: {AmlState.PENDING},
        AmlState.PENDING: {AmlState.CLEARED, AmlState.REVIEW_REQUIRED, AmlState.BLOCKED},
        AmlState.CLEARED: {AmlState.PENDING, AmlState.REVIEW_REQUIRED, AmlState.BLOCKED},
        AmlState.REVIEW_REQUIRED: {AmlState.PENDING, AmlState.CLEARED, AmlState.BLOCKED},
        AmlState.BLOCKED: {AmlState.REVIEW_REQUIRED},
    }
    if new not in allowed[old]: raise ValueError("INVALID_AML_TRANSITION")
    if new == AmlState.CLEARED and not evidence_ref: raise ValueError("VERIFIED_EVIDENCE_REQUIRED")
    if evidence_ref:evidence_ref=_validated_evidence_ref(evidence_ref)
    profile.aml_state = new; profile.aml_evidence_ref = evidence_ref or profile.aml_evidence_ref; profile.version += 1; profile.save()
    ComplianceAuditEvent.objects.create(account=profile, event_type="AML_STATE_CHANGED", actor_ref=actor_ref, state_before={"aml_state": old}, state_after={"aml_state": new})
    _enqueue(profile, "compliance.profile.updated.v1", {"aml_state": new, "version": profile.version})
    _invalidate_pending_simulation_orders_if_denied(profile)
    return profile


@transaction.atomic
def transition_sanctions(account_id, new_state, *, actor_ref="SYSTEM", evidence_ref=""):
    profile = ComplianceProfile.objects.select_for_update().get(pk=account_id)
    old, new = SanctionsState(profile.sanctions_state), SanctionsState(new_state)
    allowed = {
        SanctionsState.NOT_CHECKED: {SanctionsState.MANUAL_REVIEW, SanctionsState.POSSIBLE_MATCH, SanctionsState.CONFIRMED_MATCH, SanctionsState.CLEAR},
        SanctionsState.CLEAR: {SanctionsState.MANUAL_REVIEW, SanctionsState.POSSIBLE_MATCH, SanctionsState.CONFIRMED_MATCH},
        SanctionsState.POSSIBLE_MATCH: {SanctionsState.MANUAL_REVIEW, SanctionsState.CONFIRMED_MATCH, SanctionsState.CLEAR},
        SanctionsState.CONFIRMED_MATCH: {SanctionsState.MANUAL_REVIEW},
        SanctionsState.MANUAL_REVIEW: {SanctionsState.POSSIBLE_MATCH, SanctionsState.CONFIRMED_MATCH, SanctionsState.CLEAR},
    }
    if new not in allowed[old]: raise ValueError("INVALID_SANCTIONS_TRANSITION")
    if not evidence_ref: raise ValueError("VERIFIED_EVIDENCE_REQUIRED")
    evidence_ref=_validated_evidence_ref(evidence_ref)
    profile.sanctions_state = new; profile.sanctions_evidence_ref = evidence_ref; profile.version += 1; profile.save()
    ComplianceAuditEvent.objects.create(account=profile, event_type="SANCTIONS_STATE_CHANGED", actor_ref=actor_ref, state_before={"sanctions_state": old}, state_after={"sanctions_state": new})
    _enqueue(profile, "compliance.profile.updated.v1", {"sanctions_state": new, "version": profile.version})
    _invalidate_pending_simulation_orders_if_denied(profile)
    return profile


@transaction.atomic
def transition_jurisdiction(account_id, new_state, *, actor_ref="SYSTEM", evidence_ref=""):
    if not evidence_ref: raise ValueError("VERIFIED_EVIDENCE_REQUIRED")
    evidence_ref=_validated_evidence_ref(evidence_ref)
    profile = ComplianceProfile.objects.select_for_update().get(pk=account_id)
    old, new = JurisdictionState(profile.jurisdiction_state), JurisdictionState(new_state)
    profile.jurisdiction_state = new; profile.jurisdiction_evidence_ref = evidence_ref; profile.version += 1; profile.save()
    ComplianceAuditEvent.objects.create(account=profile, event_type="JURISDICTION_CHANGED", actor_ref=actor_ref, state_before={"jurisdiction_state": old}, state_after={"jurisdiction_state": new})
    _enqueue(profile, "compliance.profile.updated.v1", {"jurisdiction_state": new, "version": profile.version})
    _invalidate_pending_simulation_orders_if_denied(profile)
    return profile


@transaction.atomic
def add_restriction(profile, restriction_type, reason_code, source, actor, expires_at=None):
    profile = ComplianceProfile.objects.select_for_update().get(pk=profile.pk)
    try:reason_code=ReasonCode(reason_code).value
    except ValueError:raise ValueError("INVALID_REASON_CODE")
    if expires_at and expires_at <= timezone.now(): raise ValueError("INVALID_EXPIRATION")
    restriction = AccountRestriction.objects.create(account=profile, restriction_type=restriction_type, reason_code=reason_code, source=source, created_by=actor, expires_at=expires_at)
    profile.version+=1; profile.save(update_fields=["version","updated_at"])
    ComplianceAuditEvent.objects.create(account=profile, event_type="RESTRICTION_ADDED", actor_ref=str(actor.pk), reason_codes=[reason_code], state_after={"restriction_type": restriction_type})
    _enqueue(profile,"compliance.restriction.updated.v1",{"restriction_type":restriction_type,"active":True,"version":profile.version})
    _invalidate_pending_simulation_orders_if_denied(profile)
    return restriction

@transaction.atomic
def update_account_state(account_id,new_state,actor_ref="SYSTEM",reason_codes=None):
    profile=ComplianceProfile.objects.select_for_update().get(pk=account_id); new=AccountState(new_state); old=profile.account_state
    allowed={AccountState.PENDING:{AccountState.ACTIVE,AccountState.RESTRICTED,AccountState.SUSPENDED,AccountState.CLOSED},AccountState.ACTIVE:{AccountState.RESTRICTED,AccountState.SUSPENDED,AccountState.CLOSED},AccountState.RESTRICTED:{AccountState.ACTIVE,AccountState.SUSPENDED,AccountState.CLOSED},AccountState.SUSPENDED:{AccountState.RESTRICTED,AccountState.CLOSED},AccountState.CLOSED:set()}
    if new not in allowed[AccountState(old)]:raise ValueError("INVALID_ACCOUNT_TRANSITION")
    profile.account_state=new; profile.version+=1; profile.save()
    ComplianceAuditEvent.objects.create(account=profile,event_type="ACCOUNT_STATE_CHANGED",actor_ref=actor_ref,reason_codes=reason_codes or [],state_before={"account_state":old},state_after={"account_state":new})
    _enqueue(profile,"compliance.profile.updated.v1",{"account_state":new,"version":profile.version})
    _invalidate_pending_simulation_orders_if_denied(profile)
    return profile

@transaction.atomic
def create_case(profile, case_type, priority, reason_codes, actor):
    try:reason_codes=[ReasonCode(value).value for value in reason_codes]
    except (TypeError,ValueError):raise ValueError("INVALID_REASON_CODE")
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
    supplied=metadata if isinstance(metadata,dict) else {}
    allowed_metadata={"CASE_ASSIGNED":("assigned_to_id",),"CASE_NOTE_ADDED":("note_ref",),"CASE_ESCALATED":("reason_code",),"CASE_APPROVED":("resolution_code",),"CASE_REJECTED":("resolution_code",),"CASE_CLOSED":("resolution_code",)}
    safe_metadata={key:_validated_evidence_ref(str(supplied[key])[:128]) for key in allowed_metadata[event_type] if supplied.get(key)}
    if event_type=="CASE_ASSIGNED":
        from integrations.models import OrganizationMembership
        assigned_id=safe_metadata.get("assigned_to_id")
        membership=OrganizationMembership.objects.filter(user_id=assigned_id,organization_id=case.account.organization_id,role__in=("compliance_analyst","compliance_manager")).first()
        if not membership: raise ValueError("INVALID_CASE_ASSIGNEE")
        case.assigned_to_id=assigned_id
    event=ComplianceCaseEvent.objects.create(case=case,event_type=event_type,actor=actor,metadata=safe_metadata)
    if event_type in transitions:
        case.status=transitions[event_type]
        if event_type in ("CASE_APPROVED","CASE_REJECTED"): case.resolved_at=timezone.now(); case.resolution=transitions[event_type]
        case.save()
        ComplianceAuditEvent.objects.create(account=case.account,event_type="CASE_RESOLUTION" if event_type in ("CASE_APPROVED","CASE_REJECTED") else event_type,actor_ref=str(actor.pk),reason_codes=case.reason_codes,state_after={"case_id":str(case.pk),"status":case.status})
    return event

@transaction.atomic
def request_override(profile, control, new_state, reason, requester, expires_at=None, evidence_ref=""):
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
    if (control=="KYC_STATE" and new_state==KycState.APPROVED) or (control=="AML_STATE" and new_state==AmlState.CLEARED) or (control=="SANCTIONS_STATE" and new_state==SanctionsState.CLEAR):
        if not evidence_ref: raise ValueError("VERIFIED_EVIDENCE_REQUIRED")
    if evidence_ref:evidence_ref=_validated_evidence_ref(evidence_ref)
    override=ComplianceOverride.objects.create(account=profile,control=control,previous_state=current,new_state=new_state,reason=reason,evidence_ref=evidence_ref,requested_by=requester,expires_at=expires_at)
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
        profile.version+=1; profile.save(update_fields=["version","updated_at"])
        event_type="RESTRICTION_REMOVED"
    else:
        field={"KYC_STATE":"kyc_state","AML_STATE":"aml_state","SANCTIONS_STATE":"sanctions_state"}.get(override.control)
        if not field or getattr(profile,field) != override.previous_state: raise ValueError("OVERRIDE_STALE")
        setattr(profile,field,override.new_state); profile.version+=1; profile.save()
        event_type={"KYC_STATE":"KYC_STATE_CHANGED","AML_STATE":"AML_STATE_CHANGED","SANCTIONS_STATE":"SANCTIONS_STATE_CHANGED"}[override.control]
    override.approved_by=checker; override.approved_at=timezone.now(); override.full_clean(); override.save(update_fields=["approved_by","approved_at"])
    ComplianceAuditEvent.objects.create(account=profile,event_type=event_type,actor_ref=str(checker.pk),state_before={"control":override.control,"state":override.previous_state},state_after={"state":override.new_state,"override_id":str(override.pk)})
    ComplianceAuditEvent.objects.create(account=profile,event_type="MANUAL_OVERRIDE",actor_ref=str(checker.pk),state_before={"control":override.control,"state":override.previous_state},state_after={"state":override.new_state,"override_id":str(override.pk)})
    if event_type=="RESTRICTION_REMOVED":_enqueue(profile,"compliance.restriction.updated.v1",{"restriction_id":override.control.split(":",1)[1],"active":False,"version":profile.version})
    else:_enqueue(profile,"compliance.profile.updated.v1",{"version":profile.version})
    _invalidate_pending_simulation_orders_if_denied(profile)
    return override
