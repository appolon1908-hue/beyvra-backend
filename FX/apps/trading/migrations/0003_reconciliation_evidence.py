import uuid
from django.db import migrations, models
import django.db.models.deletion

IMMUTABLE_SQL="""
CREATE OR REPLACE FUNCTION trading_reject_reconciliation_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'RECONCILIATION_EVIDENCE_APPEND_ONLY'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trading_reconciliation_run_append_only BEFORE UPDATE OR DELETE ON canonical_trading_reconciliationrun FOR EACH ROW WHEN (OLD.status <> 'RUNNING') EXECUTE FUNCTION trading_reject_reconciliation_mutation();
CREATE TRIGGER trading_reconciliation_violation_append_only BEFORE UPDATE OR DELETE ON canonical_trading_reconciliationviolation FOR EACH ROW EXECUTE FUNCTION trading_reject_reconciliation_mutation();
"""
IMMUTABLE_REVERSE_SQL = "DROP TRIGGER IF EXISTS trading_reconciliation_violation_append_only ON canonical_trading_reconciliationviolation; DROP TRIGGER IF EXISTS trading_reconciliation_run_append_only ON canonical_trading_reconciliationrun; DROP FUNCTION IF EXISTS trading_reject_reconciliation_mutation();"


def install_immutability(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(IMMUTABLE_SQL)


def remove_immutability(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(IMMUTABLE_REVERSE_SQL)

class Migration(migrations.Migration):
    dependencies=[("canonical_trading","0002_simulated_trading")]
    operations=[
        migrations.CreateModel(name="ReconciliationRun",fields=[("id",models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),("environment",models.CharField(max_length=32)),("simulation",models.BooleanField(default=True)),("scope",models.CharField(default="full",max_length=32)),("started_at",models.DateTimeField()),("completed_at",models.DateTimeField(null=True)),("status",models.CharField(choices=[("RUNNING","Running"),("PASS","Pass"),("FAIL","Fail")],default="RUNNING",max_length=16)),("policy_version",models.CharField(max_length=32)),("candidate_sha",models.CharField(max_length=64)),("summary_hash",models.CharField(blank=True,max_length=64)),("check_count",models.PositiveIntegerField(default=0)),("violation_count",models.PositiveIntegerField(default=0))]),
        migrations.CreateModel(name="ReconciliationViolation",fields=[("id",models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),("check_code",models.CharField(max_length=64)),("severity",models.CharField(max_length=16)),("entity_type",models.CharField(max_length=32)),("opaque_entity_ref",models.CharField(max_length=64)),("evidence_hash",models.CharField(max_length=64)),("detected_at",models.DateTimeField(auto_now_add=True)),("run",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="violations",to="canonical_trading.reconciliationrun"))]),
        migrations.RunPython(install_immutability, remove_immutability),
    ]
