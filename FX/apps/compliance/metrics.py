from prometheus_client import Counter, Gauge

profiles_total=Gauge("beyvra_compliance_profiles_total","Compliance profiles")
kyc_state_total=Gauge("beyvra_kyc_state_total","KYC profiles by state",["state"])
aml_state_total=Gauge("beyvra_aml_state_total","AML profiles by state",["state"])
restrictions_active=Gauge("beyvra_compliance_restrictions_active","Active restrictions",["type"])
cases_open=Gauge("beyvra_compliance_cases_open","Open compliance cases",["status"])
provider_failures_total=Counter("beyvra_compliance_provider_failures_total","Provider failures",["operation"])
eligibility_decisions_total=Counter("beyvra_compliance_eligibility_decisions_total","Eligibility decisions",["capability","result","reason"])
