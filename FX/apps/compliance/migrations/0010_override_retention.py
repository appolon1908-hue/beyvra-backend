from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0009_authority_state_constraints")]
    operations = [
        migrations.RunSQL(
            "CREATE TRIGGER compliance_override_retention BEFORE DELETE ON canonical_compliance_complianceoverride FOR EACH ROW EXECUTE FUNCTION beyvra_compliance_reject_evidence_mutation();",
            "DROP TRIGGER IF EXISTS compliance_override_retention ON canonical_compliance_complianceoverride;",
        ),
    ]
