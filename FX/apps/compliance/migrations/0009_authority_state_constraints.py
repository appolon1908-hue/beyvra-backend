from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0008_compliance_profile_retention")]
    operations = [
        migrations.AddConstraint(model_name="complianceprofile", constraint=models.CheckConstraint(condition=models.Q(("account_state__in", ["PENDING","ACTIVE","RESTRICTED","SUSPENDED","CLOSED"])), name="valid_compliance_account_state")),
        migrations.AddConstraint(model_name="complianceprofile", constraint=models.CheckConstraint(condition=models.Q(("kyc_state__in", ["NOT_STARTED","PENDING","IN_REVIEW","APPROVED","REJECTED","EXPIRED","REQUIRES_UPDATE"])), name="valid_compliance_kyc_state")),
        migrations.AddConstraint(model_name="complianceprofile", constraint=models.CheckConstraint(condition=models.Q(("aml_state__in", ["NOT_SCREENED","PENDING","CLEARED","REVIEW_REQUIRED","BLOCKED"])), name="valid_compliance_aml_state")),
        migrations.AddConstraint(model_name="complianceprofile", constraint=models.CheckConstraint(condition=models.Q(("sanctions_state__in", ["NOT_CHECKED","CLEAR","POSSIBLE_MATCH","CONFIRMED_MATCH","MANUAL_REVIEW"])), name="valid_compliance_sanctions_state")),
        migrations.AddConstraint(model_name="complianceprofile", constraint=models.CheckConstraint(condition=models.Q(("jurisdiction_state__in", ["SUPPORTED","LIMITED","RESTRICTED","UNKNOWN"])), name="valid_compliance_jurisdiction_state")),
        migrations.AddConstraint(model_name="accountrestriction", constraint=models.CheckConstraint(condition=models.Q(("restriction_type__in", ["TRADING_DISABLED","DEPOSITS_DISABLED","WITHDRAWALS_DISABLED","TRANSFERS_DISABLED","MARKET_DATA_LIMITED","ACCOUNT_READ_ONLY","MANUAL_REVIEW_REQUIRED"])), name="valid_compliance_restriction_type")),
        migrations.AddConstraint(model_name="compliancecase", constraint=models.CheckConstraint(condition=models.Q(("status__in", ["OPEN","IN_REVIEW","ESCALATED","RESOLVED_APPROVED","RESOLVED_REJECTED","CLOSED"])), name="valid_compliance_case_status")),
        migrations.AddConstraint(model_name="eligibilitydecision", constraint=models.CheckConstraint(condition=models.Q(("capability__in", ["TRADING","DEPOSIT","WITHDRAWAL","TRANSFER"])), name="valid_eligibility_capability")),
        migrations.AddConstraint(model_name="eligibilitydecision", constraint=models.CheckConstraint(condition=models.Q(("result__in", ["ALLOWED","DENIED","REVIEW_REQUIRED"])), name="valid_eligibility_result")),
        migrations.AddConstraint(model_name="complianceprovidergovernance", constraint=models.CheckConstraint(condition=models.Q(("state__in", ["DISCOVERED","CONFIGURED","CREDENTIAL_PRESENT","TECHNICALLY_CERTIFIED","SECURITY_APPROVED","COMPLIANCE_APPROVED","STAGING_APPROVED","PRODUCTION_APPROVED","DISABLED"])), name="valid_compliance_provider_state")),
    ]
