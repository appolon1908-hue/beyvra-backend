from prometheus_client import Counter, Gauge

profiles_total=Gauge("beyvra_compliance_profiles_total","Compliance profiles")
kyc_state_total=Gauge("beyvra_kyc_state_total","KYC profiles by state",["state"])
aml_state_total=Gauge("beyvra_aml_state_total","AML profiles by state",["state"])
restrictions_active=Gauge("beyvra_compliance_restrictions_active","Active restrictions",["type"])
cases_open=Gauge("beyvra_compliance_cases_open","Open compliance cases",["status"])
provider_failures_total=Counter("beyvra_compliance_provider_failures_total","Provider failures",["operation"])
eligibility_decisions_total=Counter("beyvra_compliance_eligibility_decisions_total","Eligibility decisions",["capability","result","reason"])
eligibility_engine_failures_total=Counter("beyvra_compliance_eligibility_engine_failures_total","Eligibility engine failures")
event_processing_failures_total=Counter("beyvra_compliance_event_processing_failures_total","Compliance event failures",["stage"])
reconciliation_violations=Gauge("beyvra_compliance_reconciliation_violations","Compliance reconciliation violations",["kind"])

def refresh_compliance_metrics():
    from .models import AccountRestriction, ComplianceCase, ComplianceProfile
    profiles_total.set(ComplianceProfile.objects.count())
    for state in ("NOT_STARTED","PENDING","IN_REVIEW","APPROVED","REJECTED","EXPIRED","REQUIRES_UPDATE"):kyc_state_total.labels(state=state).set(ComplianceProfile.objects.filter(kyc_state=state).count())
    for state in ("NOT_SCREENED","PENDING","CLEARED","REVIEW_REQUIRED","BLOCKED"):aml_state_total.labels(state=state).set(ComplianceProfile.objects.filter(aml_state=state).count())
    for value in ("TRADING_DISABLED","DEPOSITS_DISABLED","WITHDRAWALS_DISABLED","TRANSFERS_DISABLED","MARKET_DATA_LIMITED","ACCOUNT_READ_ONLY","MANUAL_REVIEW_REQUIRED"):restrictions_active.labels(type=value).set(AccountRestriction.objects.filter(active=True,restriction_type=value).count())
    for state in ("OPEN","IN_REVIEW","ESCALATED"):cases_open.labels(status=state).set(ComplianceCase.objects.filter(status=state).count())
