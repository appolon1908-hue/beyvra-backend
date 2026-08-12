import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name="ProcessedEvent", fields=[
            ("event_id", models.UUIDField(primary_key=True, serialize=False)),
            ("event_type", models.CharField(max_length=128)),
            ("tenant_ref", models.UUIDField()),
            ("payload_hash", models.CharField(max_length=64)),
            ("processed_at", models.DateTimeField(auto_now_add=True)),
        ], options={"db_table": "financial_inbox"}),
        migrations.CreateModel(name="DeadLetterEvent", fields=[
            ("event_id", models.UUIDField(primary_key=True, serialize=False)),
            ("failure_type", models.CharField(max_length=64)),
            ("retry_count", models.PositiveIntegerField(default=0)),
            ("first_failed_at", models.DateTimeField(auto_now_add=True)),
            ("last_failed_at", models.DateTimeField(auto_now=True)),
            ("safe_error_reference", models.CharField(max_length=128)),
        ], options={"db_table": "financial_dead_letters"}),
        migrations.CreateModel(name="FinancialIncident", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("severity", models.CharField(max_length=16)),
            ("type", models.CharField(max_length=64)),
            ("detected_at", models.DateTimeField(auto_now_add=True)),
            ("candidate_sha", models.CharField(max_length=40)),
            ("environment", models.CharField(max_length=24)),
            ("safe_summary", models.CharField(max_length=500)),
            ("status", models.CharField(default="OPEN", max_length=24)),
            ("resolved_at", models.DateTimeField(blank=True, null=True)),
            ("evidence_hash", models.CharField(max_length=64)),
        ], options={"db_table": "financial_incidents"}),
    ]
