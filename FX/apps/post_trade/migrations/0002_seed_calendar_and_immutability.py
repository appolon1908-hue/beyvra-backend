from datetime import date

from django.db import migrations


def seed_calendar(apps, schema_editor):
    Calendar = apps.get_model("post_trade", "SettlementCalendar")
    Calendar.objects.get_or_create(code="SIM-CRYPTO-INSTANT", policy_version="post-trade-simulation-2026-08-v1", defaults={"asset_class": "CRYPTO", "venue_id": "SIMULATED", "currency": "USD", "settlement_convention": "INSTANT", "timezone": "UTC", "calendar_ref": "SIMULATION_24X7", "holidays": [], "effective_from": date(2020, 1, 1)})


POSTGRES_TRIGGER = """
CREATE OR REPLACE FUNCTION post_trade_reject_evidence_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'POST_TRADE_EVIDENCE_APPEND_ONLY'; END;
$$ LANGUAGE plpgsql;
CREATE OR REPLACE FUNCTION post_trade_protect_trade_history() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' OR (to_jsonb(OLD) - 'trade_state' - 'version' - 'updated_at') IS DISTINCT FROM (to_jsonb(NEW) - 'trade_state' - 'version' - 'updated_at') THEN
    RAISE EXCEPTION 'DESTRUCTIVE_TRADE_EDIT';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER post_trade_trade_history_guard BEFORE UPDATE OR DELETE ON post_trade_trade FOR EACH ROW EXECUTE FUNCTION post_trade_protect_trade_history();
CREATE TRIGGER post_trade_audit_no_update_delete BEFORE UPDATE OR DELETE ON post_trade_posttradeaudit FOR EACH ROW EXECUTE FUNCTION post_trade_reject_evidence_mutation();
CREATE TRIGGER post_trade_confirmation_no_delete BEFORE UPDATE OR DELETE ON post_trade_tradeconfirmation FOR EACH ROW EXECUTE FUNCTION post_trade_reject_evidence_mutation();
CREATE TRIGGER post_trade_effect_no_update_delete BEFORE UPDATE OR DELETE ON post_trade_tradepositioneffect FOR EACH ROW EXECUTE FUNCTION post_trade_reject_evidence_mutation();
"""

POSTGRES_REVERSE = """
DROP TRIGGER IF EXISTS post_trade_audit_no_update_delete ON post_trade_posttradeaudit;
DROP TRIGGER IF EXISTS post_trade_confirmation_no_delete ON post_trade_tradeconfirmation;
DROP TRIGGER IF EXISTS post_trade_effect_no_update_delete ON post_trade_tradepositioneffect;
DROP TRIGGER IF EXISTS post_trade_trade_history_guard ON post_trade_trade;
DROP FUNCTION IF EXISTS post_trade_reject_evidence_mutation();
DROP FUNCTION IF EXISTS post_trade_protect_trade_history();
"""


def install_postgres_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(POSTGRES_TRIGGER)


def remove_postgres_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(POSTGRES_REVERSE)


class Migration(migrations.Migration):
    dependencies = [("post_trade", "0001_initial")]
    operations = [migrations.RunPython(seed_calendar, migrations.RunPython.noop), migrations.RunPython(install_postgres_triggers, remove_postgres_triggers)]
