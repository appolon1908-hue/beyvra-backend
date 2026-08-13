from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0004_remove_complianceoutboxevent")]
    operations = [
        migrations.AlterField(
            model_name="complianceprovidergovernance",
            name="state",
            field=models.CharField(
                choices=[
                    ("DISCOVERED", "DISCOVERED"), ("CONFIGURED", "CONFIGURED"),
                    ("CREDENTIAL_PRESENT", "CREDENTIAL_PRESENT"),
                    ("TECHNICALLY_CERTIFIED", "TECHNICALLY_CERTIFIED"),
                    ("SECURITY_APPROVED", "SECURITY_APPROVED"),
                    ("COMPLIANCE_APPROVED", "COMPLIANCE_APPROVED"),
                    ("STAGING_APPROVED", "STAGING_APPROVED"),
                    ("PRODUCTION_APPROVED", "PRODUCTION_APPROVED"),
                    ("DISABLED", "DISABLED"),
                ],
                default="DISABLED",
                max_length=32,
            ),
        ),
        migrations.RunSQL(
            "CREATE TRIGGER compliance_eligibility_decision_append_only BEFORE UPDATE OR DELETE ON canonical_compliance_eligibilitydecision FOR EACH ROW EXECUTE FUNCTION beyvra_compliance_reject_evidence_mutation();",
            "DROP TRIGGER IF EXISTS compliance_eligibility_decision_append_only ON canonical_compliance_eligibilitydecision;",
        ),
    ]
