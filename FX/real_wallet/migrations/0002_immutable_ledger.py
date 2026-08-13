from django.db import migrations


FLAGS = (
    "real_wallet_read_enabled",
    "real_wallet_deposits_enabled",
    "real_wallet_withdrawals_enabled",
    "real_wallet_internal_transfers_enabled",
    "real_trading_enabled",
    "external_execution_enabled",
    "internal_execution_enabled",
)


def seed_disabled_flags(apps, schema_editor):
    FeatureFlag = apps.get_model("real_wallet", "FeatureFlag")
    FeatureFlag.objects.bulk_create([FeatureFlag(key=key, enabled=False) for key in FLAGS], ignore_conflicts=True)


def remove_flags(apps, schema_editor):
    apps.get_model("real_wallet", "FeatureFlag").objects.filter(key__in=FLAGS).delete()


def install_ledger_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        CREATE OR REPLACE FUNCTION real_wallet_reject_posted_entry_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM real_ledger_transactions
                WHERE id = OLD.transaction_id AND status IN ('POSTED', 'REVERSED')
            ) THEN
                RAISE EXCEPTION 'posted ledger entries are immutable';
            END IF;
            RETURN OLD;
        END; $$;
        DROP TRIGGER IF EXISTS real_wallet_entry_update_guard ON real_ledger_entries;
        CREATE TRIGGER real_wallet_entry_update_guard
        BEFORE UPDATE OR DELETE ON real_ledger_entries
        FOR EACH ROW EXECUTE FUNCTION real_wallet_reject_posted_entry_mutation();
        """
    )


def remove_ledger_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS real_wallet_entry_update_guard ON real_ledger_entries;")
    schema_editor.execute("DROP FUNCTION IF EXISTS real_wallet_reject_posted_entry_mutation();")


class Migration(migrations.Migration):
    dependencies = [("real_wallet", "0001_initial")]
    operations = [
        migrations.RunPython(seed_disabled_flags, remove_flags),
        migrations.RunPython(install_ledger_guards, remove_ledger_guards),
    ]
