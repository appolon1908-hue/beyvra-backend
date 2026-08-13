from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("financial_boundary", "0002_event_boundary")]
    operations = [
        migrations.CreateModel(
            name="FinancialProjectionCursor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tenant_ref", models.UUIDField()),
                ("subject_ref", models.CharField(max_length=64)),
                ("event_type", models.CharField(max_length=64)),
                ("last_sequence", models.PositiveBigIntegerField(default=0)),
                ("last_event_id", models.UUIDField(blank=True, null=True)),
                ("snapshot_version", models.PositiveBigIntegerField(default=0)),
                ("projection", models.JSONField(blank=True, default=dict)),
                ("projection_hash", models.CharField(blank=True, default="", max_length=64)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "financial_projection_cursors"},
        ),
        migrations.AddConstraint(
            model_name="financialprojectioncursor",
            constraint=models.UniqueConstraint(
                fields=("tenant_ref", "subject_ref", "event_type"),
                name="financial_projection_cursor_scope_unique",
            ),
        ),
    ]
