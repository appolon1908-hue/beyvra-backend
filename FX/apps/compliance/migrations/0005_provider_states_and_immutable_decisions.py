from django.db import migrations, models


FORWARD = "CREATE TRIGGER compliance_eligibility_decision_append_only BEFORE UPDATE OR DELETE ON canonical_compliance_eligibilitydecision FOR EACH ROW EXECUTE FUNCTION beyvra_compliance_reject_evidence_mutation();"
REVERSE = "DROP TRIGGER IF EXISTS compliance_eligibility_decision_append_only ON canonical_compliance_eligibilitydecision;"


def install_decision_append_only(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FORWARD)


def remove_decision_append_only(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(REVERSE)


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
        migrations.RunPython(install_decision_append_only, remove_decision_append_only),
    ]
