from django.db import migrations


TABLES = (
    "reference_data_referencedataaudit",
    "reference_data_marketdataobservation",
    "reference_data_corporateaction",
)


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        CREATE OR REPLACE FUNCTION beyvra_reference_append_only() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'reference authority records are append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in TABLES:
        schema_editor.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION beyvra_reference_append_only();"
        )


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
    schema_editor.execute("DROP FUNCTION IF EXISTS beyvra_reference_append_only();")


class Migration(migrations.Migration):
    dependencies = [("reference_data", "0001_initial")]
    operations = [migrations.RunPython(install, uninstall)]
