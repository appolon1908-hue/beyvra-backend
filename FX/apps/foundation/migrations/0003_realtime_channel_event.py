from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("foundation", "0002_audit_append_only"),
    ]

    operations = [
        migrations.CreateModel(
            name="RealtimeChannelEvent",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("tenant_ref", models.CharField(max_length=128)),
                ("channel", models.CharField(max_length=200)),
                ("sequence", models.PositiveBigIntegerField()),
                ("event_id", models.CharField(max_length=128)),
                ("event_type", models.CharField(max_length=128)),
                ("source", models.CharField(max_length=64)),
                ("payload", models.JSONField(default=dict)),
                ("payload_hash", models.CharField(max_length=64)),
                ("occurred_at", models.DateTimeField()),
                ("server_time", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["tenant_ref", "channel", "-sequence"], name="rt_channel_latest_idx"),
                    models.Index(fields=["tenant_ref", "channel", "sequence"], name="rt_channel_resume_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_ref", "channel", "sequence"), name="rt_channel_sequence_unique"),
                    models.UniqueConstraint(fields=("tenant_ref", "channel", "payload_hash"), name="rt_channel_payload_unique"),
                ],
            },
        ),
    ]
