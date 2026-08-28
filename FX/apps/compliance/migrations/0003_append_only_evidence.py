from django.db import migrations

FORWARD="""
CREATE OR REPLACE FUNCTION beyvra_compliance_reject_evidence_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'COMPLIANCE_EVIDENCE_APPEND_ONLY'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER compliance_audit_append_only BEFORE UPDATE OR DELETE ON canonical_compliance_complianceauditevent FOR EACH ROW EXECUTE FUNCTION beyvra_compliance_reject_evidence_mutation();
CREATE TRIGGER compliance_case_event_append_only BEFORE UPDATE OR DELETE ON canonical_compliance_compliancecaseevent FOR EACH ROW EXECUTE FUNCTION beyvra_compliance_reject_evidence_mutation();
"""
REVERSE="""
DROP TRIGGER IF EXISTS compliance_audit_append_only ON canonical_compliance_complianceauditevent;
DROP TRIGGER IF EXISTS compliance_case_event_append_only ON canonical_compliance_compliancecaseevent;
DROP FUNCTION IF EXISTS beyvra_compliance_reject_evidence_mutation();
"""


def install_append_only(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FORWARD)


def remove_append_only(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(REVERSE)


class Migration(migrations.Migration):
    dependencies=[("canonical_compliance","0002_alter_complianceoverride_control")]
    operations=[migrations.RunPython(install_append_only, remove_append_only)]
