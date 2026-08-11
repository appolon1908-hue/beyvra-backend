from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql": return
    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION beyvra_surveillance_event_evidence_immutable() RETURNS trigger AS $$
        BEGIN
          IF OLD.tenant_ref IS DISTINCT FROM NEW.tenant_ref OR OLD.account_ref IS DISTINCT FROM NEW.account_ref
             OR OLD.instrument_id IS DISTINCT FROM NEW.instrument_id OR OLD.event_type IS DISTINCT FROM NEW.event_type
             OR OLD.detected_at IS DISTINCT FROM NEW.detected_at OR OLD.window_start IS DISTINCT FROM NEW.window_start
             OR OLD.window_end IS DISTINCT FROM NEW.window_end OR OLD.rule_id IS DISTINCT FROM NEW.rule_id
             OR OLD.rule_version IS DISTINCT FROM NEW.rule_version OR OLD.policy_version IS DISTINCT FROM NEW.policy_version
             OR OLD.score IS DISTINCT FROM NEW.score OR OLD.evidence_hash IS DISTINCT FROM NEW.evidence_hash
             OR OLD.evidence_safe IS DISTINCT FROM NEW.evidence_safe OR OLD.source_event_id IS DISTINCT FROM NEW.source_event_id THEN
            RAISE EXCEPTION 'surveillance evidence is immutable';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER surveillance_event_evidence_immutable BEFORE UPDATE ON surveillance_surveillanceevent
        FOR EACH ROW EXECUTE FUNCTION beyvra_surveillance_event_evidence_immutable();
        CREATE TRIGGER surveillance_case_event_append_only BEFORE UPDATE OR DELETE ON surveillance_surveillancecaseevent
        FOR EACH ROW EXECUTE FUNCTION beyvra_surveillance_append_only();
    """)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql": return
    schema_editor.execute("DROP TRIGGER IF EXISTS surveillance_event_evidence_immutable ON surveillance_surveillanceevent;")
    schema_editor.execute("DROP TRIGGER IF EXISTS surveillance_case_event_append_only ON surveillance_surveillancecaseevent;")
    schema_editor.execute("DROP FUNCTION IF EXISTS beyvra_surveillance_event_evidence_immutable();")


class Migration(migrations.Migration):
    dependencies = [("surveillance", "0003_case_timeline")]
    operations = [migrations.RunPython(install, uninstall)]
