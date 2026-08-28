from django.db import migrations


FORWARD = "CREATE TRIGGER compliance_override_retention BEFORE DELETE ON canonical_compliance_complianceoverride FOR EACH ROW EXECUTE FUNCTION beyvra_compliance_reject_evidence_mutation();"
REVERSE = "DROP TRIGGER IF EXISTS compliance_override_retention ON canonical_compliance_complianceoverride;"


def install_override_retention(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FORWARD)


def remove_override_retention(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(REVERSE)


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0009_authority_state_constraints")]
    operations = [
        migrations.RunPython(install_override_retention, remove_override_retention),
    ]
