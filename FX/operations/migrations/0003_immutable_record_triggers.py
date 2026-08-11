from django.db import migrations

TABLES = (
    "operations_auditevent",
    "operations_securityevent",
    "operations_supportcaseevent",
    "operations_transactionhistoryentry",
    "operations_statement",
)


def add_immutable_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION operations_reject_immutable_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'immutable operational record';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        for table in TABLES:
            cursor.execute(
                f"""
                CREATE TRIGGER reject_immutable_mutation
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION operations_reject_immutable_mutation();
                """
            )


def remove_immutable_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(
                f"DROP TRIGGER IF EXISTS reject_immutable_mutation ON {table};"
            )
        cursor.execute(
            "DROP FUNCTION IF EXISTS operations_reject_immutable_mutation();"
        )


class Migration(migrations.Migration):
    dependencies = [("operations", "0002_reconciliationcheck_accountdeletionrequest")]

    operations = [
        migrations.RunPython(add_immutable_triggers, remove_immutable_triggers),
    ]
