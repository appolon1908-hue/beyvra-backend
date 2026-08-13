from django.db import migrations


def add_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TRIGGER reject_immutable_mutation
            BEFORE UPDATE OR DELETE ON operations_tradeconfirmation
            FOR EACH ROW EXECUTE FUNCTION operations_reject_immutable_mutation();
            """
        )


def remove_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "DROP TRIGGER IF EXISTS reject_immutable_mutation "
            "ON operations_tradeconfirmation;"
        )


class Migration(migrations.Migration):
    dependencies = [("operations", "0005_reporting_authorities")]

    operations = [migrations.RunPython(add_trigger, remove_trigger)]
