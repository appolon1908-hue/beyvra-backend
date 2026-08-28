import django.db.models.deletion
from django.db import migrations, models


FORWARD = "CREATE TRIGGER compliance_profile_retention_hold BEFORE DELETE ON canonical_compliance_complianceprofile FOR EACH ROW EXECUTE FUNCTION beyvra_compliance_reject_evidence_mutation();"
REVERSE = "DROP TRIGGER IF EXISTS compliance_profile_retention_hold ON canonical_compliance_complianceprofile;"


def install_profile_retention(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FORWARD)


def remove_profile_retention(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(REVERSE)


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0007_authority_evidence_references")]
    operations = [
        migrations.AlterField(
            model_name="complianceprofile",
            name="organization",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="compliance_profiles", to="integrations.organization"),
        ),
        migrations.RunPython(install_profile_retention, remove_profile_retention),
    ]
