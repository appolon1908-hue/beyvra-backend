import uuid

from django.db import migrations, models


AUDIT_GUARD_SQL = """
CREATE OR REPLACE FUNCTION financial_audit_append_only_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'financial audit is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER financial_audit_append_only
BEFORE UPDATE OR DELETE ON financial_audit
FOR EACH ROW EXECUTE FUNCTION financial_audit_append_only_guard();
"""

AUDIT_GUARD_REVERSE_SQL = """
DROP TRIGGER IF EXISTS financial_audit_append_only ON financial_audit;
DROP FUNCTION IF EXISTS financial_audit_append_only_guard();
"""


def install_audit_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(AUDIT_GUARD_SQL)


def remove_audit_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(AUDIT_GUARD_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("financial_boundary", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="FinancialOutboxEvent",
            fields=[
                ("event_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_type", models.CharField(max_length=128)),
                ("schema_version", models.PositiveSmallIntegerField(default=1)),
                ("occurred_at", models.DateTimeField()),
                ("correlation_id", models.UUIDField()),
                ("causation_id", models.UUIDField(blank=True, null=True)),
                ("tenant_ref", models.UUIDField()),
                ("payload", models.JSONField()),
                ("payload_hash", models.CharField(max_length=64)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("IN_FLIGHT", "In Flight"), ("PUBLISHED", "Published")], default="PENDING", max_length=16)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField()),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("safe_error_reference", models.CharField(blank=True, default="", max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "financial_outbox"},
        ),
        migrations.AddIndex(
            model_name="financialoutboxevent",
            index=models.Index(fields=["status", "next_attempt_at"], name="financial_outbox_ready_idx"),
        ),
        migrations.CreateModel(
            name="FinancialAuditEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("action", models.CharField(max_length=64)),
                ("tenant_ref", models.UUIDField()),
                ("account_ref", models.UUIDField(blank=True, null=True)),
                ("actor_ref", models.UUIDField(blank=True, null=True)),
                ("correlation_id", models.UUIDField()),
                ("subject_ref", models.CharField(blank=True, default="", max_length=128)),
                ("payload_hash", models.CharField(max_length=64)),
                ("safe_metadata", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "financial_audit"},
        ),
        migrations.AddIndex(
            model_name="financialauditevent",
            index=models.Index(fields=["tenant_ref", "occurred_at"], name="financial_audit_tenant_idx"),
        ),
        migrations.RunPython(install_audit_guard, remove_audit_guard),
    ]
