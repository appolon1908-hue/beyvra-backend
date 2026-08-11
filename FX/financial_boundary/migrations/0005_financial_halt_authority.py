import uuid

import django.db.models.deletion
from django.db import migrations, models


HALT_APPEND_ONLY_SQL = """
CREATE OR REPLACE FUNCTION financial_halt_append_only_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'financial halt history is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER financial_halt_request_append_only
BEFORE UPDATE OR DELETE ON financial_halt_requests
FOR EACH ROW EXECUTE FUNCTION financial_halt_append_only_guard();
CREATE TRIGGER financial_halt_approval_append_only
BEFORE UPDATE OR DELETE ON financial_halt_approvals
FOR EACH ROW EXECUTE FUNCTION financial_halt_append_only_guard();
"""

HALT_APPEND_ONLY_REVERSE_SQL = """
DROP TRIGGER IF EXISTS financial_halt_approval_append_only ON financial_halt_approvals;
DROP TRIGGER IF EXISTS financial_halt_request_append_only ON financial_halt_requests;
DROP FUNCTION IF EXISTS financial_halt_append_only_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("financial_boundary", "0004_destination")]
    operations = [
        migrations.CreateModel(
            name="FinancialHaltRequest",
            fields=[
                ("request_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenant_ref", models.UUIDField()),
                ("proposed_state", models.CharField(choices=[
                    ("ACTIVE", "Active"), ("READ_ONLY", "Read Only"),
                    ("WITHDRAWALS_HALTED", "Withdrawals Halted"),
                    ("FUNDING_HALTED", "Funding Halted"),
                    ("ALL_MUTATIONS_HALTED", "All Mutations Halted"),
                ], max_length=24)),
                ("requested_by", models.PositiveBigIntegerField()),
                ("reason_code", models.CharField(max_length=64)),
                ("policy_version", models.CharField(max_length=32)),
                ("correlation_id", models.UUIDField()),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "financial_halt_requests"},
        ),
        migrations.AddIndex(
            model_name="financialhaltrequest",
            index=models.Index(fields=["tenant_ref", "requested_at"], name="financial_halt_req_tenant_idx"),
        ),
        migrations.CreateModel(
            name="FinancialHaltApproval",
            fields=[
                ("approval_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("approved_by", models.PositiveBigIntegerField()),
                ("correlation_id", models.UUIDField()),
                ("approved_at", models.DateTimeField(auto_now_add=True)),
                ("request", models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="approval", to="financial_boundary.financialhaltrequest",
                )),
            ],
            options={"db_table": "financial_halt_approvals"},
        ),
        migrations.AddIndex(
            model_name="financialhaltapproval",
            index=models.Index(fields=["approved_at"], name="financial_halt_approved_idx"),
        ),
        migrations.RunSQL(HALT_APPEND_ONLY_SQL, HALT_APPEND_ONLY_REVERSE_SQL),
    ]
