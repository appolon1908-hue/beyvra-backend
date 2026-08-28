import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("financial_boundary", "0005_financial_halt_authority"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProviderWebhookInbox",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("provider", models.CharField(max_length=64)),
                ("external_event_id", models.CharField(max_length=128)),
                ("tenant_id", models.UUIDField()),
                ("payload_hash", models.CharField(max_length=64)),
                ("encrypted_payload", models.BinaryField(blank=True, null=True)),
                ("payload_reference", models.CharField(blank=True, default="", max_length=255)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("signature_timestamp", models.DateTimeField()),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("PROCESSING", "Processing"), ("PROCESSED", "Processed"), ("DEAD_LETTER", "Dead Letter")], default="PENDING", max_length=16)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("lease_owner", models.CharField(blank=True, default="", max_length=128)),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("failure_code", models.CharField(blank=True, default="", max_length=64)),
                ("request_id", models.CharField(blank=True, default="", max_length=128)),
            ],
            options={
                "db_table": "financial_provider_webhook_inbox",
                "indexes": [
                    models.Index(fields=("status", "next_attempt_at"), name="fin_webhook_ready_idx"),
                    models.Index(fields=("tenant_id", "received_at"), name="fin_webhook_tenant_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("provider", "external_event_id"), name="financial_provider_webhook_unique"),
                ],
            },
        ),
    ]
