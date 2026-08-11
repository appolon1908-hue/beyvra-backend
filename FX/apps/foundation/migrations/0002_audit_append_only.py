from django.db import migrations


def install_append_only_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        CREATE OR REPLACE FUNCTION foundation_reject_audit_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'APPLICATION_AUDIT_APPEND_ONLY';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER foundation_audit_append_only
        BEFORE UPDATE OR DELETE ON foundation_applicationauditevent
        FOR EACH ROW EXECUTE FUNCTION foundation_reject_audit_mutation();
        """
    )


def remove_append_only_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        DROP TRIGGER IF EXISTS foundation_audit_append_only
        ON foundation_applicationauditevent;
        DROP FUNCTION IF EXISTS foundation_reject_audit_mutation();
        """
    )


class Migration(migrations.Migration):
    dependencies = [("foundation", "0001_initial")]
    operations = [
        migrations.RunPython(install_append_only_trigger, remove_append_only_trigger)
    ]
