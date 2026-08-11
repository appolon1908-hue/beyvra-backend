from django.db import migrations, models


REASONS=["KYC_REQUIRED","KYC_PENDING","KYC_REJECTED","AML_REVIEW","AML_BLOCKED","SANCTIONS_REVIEW","SANCTIONS_BLOCKED","JURISDICTION_RESTRICTED","ACCOUNT_RESTRICTED","ACCOUNT_SUSPENDED","TRADING_DISABLED","DEPOSITS_DISABLED","WITHDRAWALS_DISABLED","TRANSFERS_DISABLED","MANUAL_REVIEW_REQUIRED"]


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0010_override_retention")]
    operations = [
        migrations.AlterField(model_name="accountrestriction",name="reason_code",field=models.CharField(choices=[(value,value) for value in REASONS],max_length=64)),
        migrations.AddConstraint(model_name="accountrestriction",constraint=models.CheckConstraint(condition=models.Q(("reason_code__in",REASONS)),name="valid_compliance_restriction_reason")),
    ]
