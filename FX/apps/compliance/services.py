from django.db import transaction
from django.utils import timezone
from .domain import AccountState, AmlState, EligibilityDecisionValue, EligibilityResult, JurisdictionState, KYC_TRANSITIONS, KycState, RestrictionType, SanctionsState
from .models import AccountRestriction, ComplianceAuditEvent, ComplianceOutboxEvent, ComplianceProfile, EligibilityDecision
from .metrics import eligibility_decisions_total

POLICY_VERSION = "compliance-2026-08-11.v1"


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
    ComplianceOutboxEvent.objects.create(account=profile, event_type="compliance.profile.updated.v1", payload={"account_id": str(profile.pk), "kyc_state": new, "version": profile.version})
    return profile


@transaction.atomic
def add_restriction(profile, restriction_type, reason_code, source, actor):
    restriction = AccountRestriction.objects.create(account=profile, restriction_type=restriction_type, reason_code=reason_code, source=source, created_by=actor)
    ComplianceAuditEvent.objects.create(account=profile, event_type="RESTRICTION_ADDED", actor_ref=str(actor.pk), reason_codes=[reason_code], state_after={"restriction_type": restriction_type})
    ComplianceOutboxEvent.objects.create(account=profile, event_type="compliance.restriction.updated.v1", payload={"account_id": str(profile.pk), "restriction_type": restriction_type, "active": True})
    return restriction
