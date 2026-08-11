import uuid

import django.db.models.deletion
import django.db.models.functions.datetime
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trade", "0010_trade_organization"),
        ("integrations", "0001_initial"),
        ("wallet", "0016_wallet_organization"),
    ]
    operations = [
        migrations.AlterField(
            model_name="trade",
            name="demo_result",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.CreateModel(
            name="DemoEventOutbox",
            fields=[
                ("sequence", models.BigAutoField(primary_key=True, serialize=False)),
                ("event_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("event_type", models.CharField(max_length=64)),
                ("event_version", models.PositiveSmallIntegerField(default=1)),
                ("channel", models.CharField(max_length=96)),
                ("payload", models.JSONField(default=dict)),
                ("occurred_at", models.DateTimeField(default=django.db.models.functions.datetime.Now)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("last_error_code", models.CharField(blank=True, max_length=64)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="demo_event_outbox", to="integrations.organization")),
                ("trade", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="demo_events", to="trade.trade")),
                ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="demo_event_outbox", to="wallet.wallet")),
            ],
        ),
        migrations.AddIndex(
            model_name="demoeventoutbox",
            index=models.Index(condition=models.Q(("published_at__isnull", True)), fields=["next_attempt_at", "sequence"], name="demo_outbox_pending_idx"),
        ),
        migrations.AddIndex(
            model_name="demoeventoutbox",
            index=models.Index(fields=["wallet", "sequence"], name="demo_outbox_account_idx"),
        ),
    ]
