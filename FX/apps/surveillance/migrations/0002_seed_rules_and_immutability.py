from django.db import migrations
from django.utils import timezone


RULES = (
    ("stp-v1", "SELF_TRADE_ATTEMPT", "CRITICAL", {}),
    ("restricted-v1", "RESTRICTED_INSTRUMENT_ATTEMPT", "HIGH", {}),
    ("wash-v1", "WASH_TRADE_PATTERN", "HIGH", {"minimum_trades": 4, "max_net_ratio": "0.1"}),
    ("spoof-v1", "SPOOFING_INDICATOR", "HIGH", {}),
    ("layering-v1", "LAYERING_INDICATOR", "HIGH", {"minimum_levels": 3}),
    ("cancel-ratio-v1", "EXCESSIVE_CANCEL_PATTERN", "MEDIUM", {"minimum_orders": 5, "cancel_ratio": "0.8"}),
    ("rapid-flip-v1", "RAPID_ORDER_FLIP", "MEDIUM", {"window_seconds": 30}),
    ("order-rate-v1", "ORDER_RATE_ANOMALY", "MEDIUM", {"orders_per_window": 20}),
    ("price-deviation-v1", "PRICE_DEVIATION_ORDER", "MEDIUM", {"deviation_ratio": "0.1"}),
)


def seed_rules(apps, schema_editor):
    Rule = apps.get_model("surveillance", "SurveillanceRule")
    now = timezone.now()
    for name, event_type, severity, parameters in RULES:
        Rule.objects.get_or_create(name=name, version=1, defaults={"event_type": event_type, "enabled": True, "severity": severity, "asset_class": "ALL", "parameters_json_safe": parameters, "policy_version": "surveillance-2026-08-v1", "effective_from": now})


def install_append_only(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION beyvra_surveillance_append_only() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'surveillance evidence is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ("surveillance_surveillanceaudit",):
        schema_editor.execute(f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION beyvra_surveillance_append_only();")


def uninstall_append_only(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS surveillance_surveillanceaudit_append_only ON surveillance_surveillanceaudit;")
    schema_editor.execute("DROP FUNCTION IF EXISTS beyvra_surveillance_append_only();")


class Migration(migrations.Migration):
    dependencies = [("surveillance", "0001_initial")]
    operations = [migrations.RunPython(seed_rules, migrations.RunPython.noop), migrations.RunPython(install_append_only, uninstall_append_only)]
