import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name="OutboxEvent", fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False)), ("event_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
            ("aggregate_type", models.CharField(max_length=64)), ("aggregate_id", models.CharField(max_length=128)), ("event_type", models.CharField(max_length=128)),
            ("schema_version", models.PositiveSmallIntegerField(default=1)), ("payload", models.JSONField(default=dict)), ("correlation_id", models.UUIDField()),
            ("causation_id", models.UUIDField(blank=True, null=True)), ("tenant_ref", models.CharField(max_length=128)), ("occurred_at", models.DateTimeField()),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("published_at", models.DateTimeField(blank=True, null=True)),
            ("attempt_count", models.PositiveIntegerField(default=0)), ("next_attempt_at", models.DateTimeField(blank=True, null=True)),
            ("last_error", models.CharField(blank=True, max_length=128)), ("state", models.CharField(choices=[("PENDING", "Pending"), ("CLAIMED", "Claimed"), ("PUBLISHED", "Published"), ("DEAD_LETTER", "Dead Letter")], default="PENDING", max_length=16)),
            ("claimed_at", models.DateTimeField(blank=True, null=True)),
        ], options={"indexes": [models.Index(fields=["state", "next_attempt_at", "id"], name="outbox_pending_idx")]}),
        migrations.CreateModel(name="ProcessedEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("event_id", models.UUIDField()),
            ("consumer_name", models.CharField(max_length=128)), ("payload_hash", models.CharField(max_length=64)), ("processed_at", models.DateTimeField(auto_now_add=True)),
        ], options={"constraints": [models.UniqueConstraint(fields=("event_id", "consumer_name"), name="processed_event_consumer_unique")]}),
        migrations.CreateModel(name="IdempotencyRecord", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("key", models.CharField(max_length=255)),
            ("tenant_ref", models.CharField(max_length=128)), ("actor_ref", models.CharField(max_length=128)), ("endpoint", models.CharField(max_length=255)),
            ("method", models.CharField(max_length=16)), ("request_hash", models.CharField(max_length=64)), ("response_status", models.PositiveSmallIntegerField(null=True)),
            ("response_body", models.JSONField(null=True)), ("resource_type", models.CharField(blank=True, max_length=64)), ("resource_id", models.CharField(blank=True, max_length=128)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("expires_at", models.DateTimeField()),
        ], options={"constraints": [models.UniqueConstraint(fields=("key", "tenant_ref", "actor_ref", "endpoint", "method"), name="idempotency_scope_unique")]}),
        migrations.CreateModel(name="ApplicationAuditEvent", fields=[
            ("event_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("actor_ref", models.CharField(max_length=128)),
            ("action", models.CharField(max_length=128)), ("resource_type", models.CharField(max_length=64)), ("resource_id", models.CharField(max_length=128)),
            ("before_hash", models.CharField(blank=True, max_length=64)), ("after_hash", models.CharField(blank=True, max_length=64)), ("request_id", models.CharField(max_length=128)),
            ("correlation_id", models.UUIDField()), ("context", models.JSONField(default=dict)), ("reason", models.CharField(max_length=255)), ("occurred_at", models.DateTimeField()),
        ]),
        migrations.CreateModel(name="TradingControl", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("scope", models.CharField(choices=[("PLATFORM", "Platform"), ("ASSET_CLASS", "Asset Class"), ("INSTRUMENT", "Instrument"), ("ACCOUNT", "Account"), ("PROVIDER", "Provider")], max_length=16)),
            ("scope_ref", models.CharField(default="*", max_length=128)), ("state", models.CharField(choices=[("ACTIVE", "Active"), ("CLOSE_ONLY", "Close Only"), ("CANCEL_ONLY", "Cancel Only"), ("HALTED", "Halted"), ("MAINTENANCE", "Maintenance")], max_length=16)),
            ("reason", models.CharField(max_length=255)), ("request_id", models.CharField(max_length=128)), ("changed_by_ref", models.CharField(max_length=128)), ("created_at", models.DateTimeField(auto_now_add=True)),
        ], options={"constraints": [models.UniqueConstraint(fields=("scope", "scope_ref"), name="trading_control_scope_unique")]}),
    ]
