from prometheus_client import Counter, Gauge
from django.db.models import Q

profiles_total=Gauge("beyvra_compliance_profiles_total","Compliance profiles")
kyc_state_total=Gauge("beyvra_kyc_state_total","KYC profiles by state",["state"])
aml_state_total=Gauge("beyvra_aml_state_total","AML profiles by state",["state"])
restrictions_active=Gauge("beyvra_compliance_restrictions_active","Active restrictions",["type"])
cases_open=Gauge("beyvra_compliance_cases_open","Open compliance cases",["status"])
case_oldest_age_seconds=Gauge("beyvra_compliance_case_oldest_age_seconds","Age of oldest unresolved compliance case")
provider_health=Gauge("beyvra_compliance_provider_health","Compliance providers by bounded governance state",["state"])
provider_failures_total=Counter("beyvra_compliance_provider_failures_total","Provider failures",["operation"])
eligibility_decisions_total=Counter("beyvra_compliance_eligibility_decisions_total","Eligibility decisions",["capability","result","reason"])
eligibility_engine_failures_total=Counter("beyvra_compliance_eligibility_engine_failures_total","Eligibility engine failures")
event_processing_failures_total=Counter("beyvra_compliance_event_processing_failures_total","Compliance event failures",["stage"])
webhook_signature_failures_total=Counter("beyvra_compliance_webhook_signature_failures_total","Rejected compliance webhook signatures")
reconciliation_violations=Gauge("beyvra_compliance_reconciliation_violations","Compliance reconciliation violations",["kind"])

def refresh_compliance_metrics():
    from collections import Counter as ValueCounter
    from django.utils import timezone
    from .models import AccountRestriction, ComplianceCase, ComplianceProfile, ComplianceProviderGovernance
    now=timezone.now()
    from .services import effective_profile_states
    profiles=list(ComplianceProfile.objects.prefetch_related("overrides")); profiles_total.set(len(profiles)); effective=[effective_profile_states(profile,now) for profile in profiles]; kyc_counts=ValueCounter(str(value["kyc_state"]) for value in effective); aml_counts=ValueCounter(str(value["aml_state"]) for value in effective)
    for state in ("NOT_STARTED","PENDING","IN_REVIEW","APPROVED","REJECTED","EXPIRED","REQUIRES_UPDATE"):kyc_state_total.labels(state=state).set(kyc_counts[state])
    for state in ("NOT_SCREENED","PENDING","CLEARED","REVIEW_REQUIRED","BLOCKED"):aml_state_total.labels(state=state).set(aml_counts[state])
    for value in ("TRADING_DISABLED","DEPOSITS_DISABLED","WITHDRAWALS_DISABLED","TRANSFERS_DISABLED","MARKET_DATA_LIMITED","ACCOUNT_READ_ONLY","MANUAL_REVIEW_REQUIRED"):restrictions_active.labels(type=value).set(AccountRestriction.objects.filter(active=True,restriction_type=value).filter(Q(expires_at__isnull=True)|Q(expires_at__gt=now)).count())
    for state in ("OPEN","IN_REVIEW","ESCALATED"):cases_open.labels(status=state).set(ComplianceCase.objects.filter(status=state).count())
    oldest=ComplianceCase.objects.filter(status__in=("OPEN","IN_REVIEW","ESCALATED")).order_by("created_at").values_list("created_at",flat=True).first(); case_oldest_age_seconds.set(max(0,(now-oldest).total_seconds()) if oldest else 0)
    for state in ("DISCOVERED","CONFIGURED","CREDENTIAL_PRESENT","TECHNICALLY_CERTIFIED","SECURITY_APPROVED","COMPLIANCE_APPROVED","STAGING_APPROVED","PRODUCTION_APPROVED","DISABLED"):provider_health.labels(state=state).set(ComplianceProviderGovernance.objects.filter(state=state).count())
