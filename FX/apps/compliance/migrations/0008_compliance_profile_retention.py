import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0007_authority_evidence_references")]
    operations = [
        migrations.AlterField(
            model_name="complianceprofile",
            name="organization",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="compliance_profiles", to="integrations.organization"),
        ),
        migrations.RunSQL(
            "CREATE TRIGGER compliance_profile_retention_hold BEFORE DELETE ON canonical_compliance_complianceprofile FOR EACH ROW EXECUTE FUNCTION beyvra_compliance_reject_evidence_mutation();",
            "DROP TRIGGER IF EXISTS compliance_profile_retention_hold ON canonical_compliance_complianceprofile;",
        ),
    ]
