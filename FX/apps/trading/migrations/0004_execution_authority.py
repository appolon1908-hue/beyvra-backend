import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("canonical_trading", "0003_reconciliation_evidence")]
    operations = [
        migrations.CreateModel(name="ExecutionProviderRecord", fields=[
            ("provider_id", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("display_name", models.CharField(max_length=128)),
            ("mode", models.CharField(choices=[("SIMULATION", "Simulation"), ("PAPER", "Paper"), ("LIVE", "Live")], max_length=16)),
            ("enabled", models.BooleanField(default=False)),
            ("health", models.CharField(choices=[("HEALTHY", "Healthy"), ("DEGRADED", "Degraded"), ("UNAVAILABLE", "Unavailable"), ("HALTED", "Halted")], default="HALTED", max_length=16)),
            ("capabilities", models.JSONField(default=dict)), ("supported_asset_classes", models.JSONField(default=list)),
            ("supported_order_types", models.JSONField(default=list)), ("supported_venues", models.JSONField(default=list)),
            ("circuit_open_until", models.DateTimeField(blank=True, null=True)), ("consecutive_failures", models.PositiveIntegerField(default=0)),
            ("updated_at", models.DateTimeField(auto_now=True)),
        ]),
        migrations.CreateModel(name="ExecutionVenue", fields=[
            ("venue_id", models.CharField(max_length=64, primary_key=True, serialize=False)), ("display_name", models.CharField(max_length=128)),
            ("asset_classes", models.JSONField(default=list)), ("order_types", models.JSONField(default=list)), ("active", models.BooleanField(default=False)),
            ("delayed", models.BooleanField(default=False)), ("metadata", models.JSONField(default=dict)), ("updated_at", models.DateTimeField(auto_now=True)),
        ]),
        migrations.CreateModel(name="ExecutionRoutingDecision", fields=[
            ("decision_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("tenant_ref", models.CharField(max_length=128)), ("subject_ref", models.CharField(max_length=128)), ("mode", models.CharField(max_length=16)),
            ("status", models.CharField(choices=[("SELECTED", "Selected"), ("DENIED", "Denied"), ("UNKNOWN", "Unknown")], max_length=16)),
            ("selected_provider_id", models.CharField(blank=True, max_length=64)), ("selected_venue_id", models.CharField(blank=True, max_length=64)),
            ("policy_version", models.CharField(max_length=32)), ("candidate_evidence", models.JSONField(default=list)), ("exclusion_reasons", models.JSONField(default=list)),
            ("market_snapshot_hash", models.CharField(max_length=64)), ("request_hash", models.CharField(max_length=64)),
            ("reference_price", models.DecimalField(decimal_places=18, max_digits=36)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("order", models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="routing_decisions", to="canonical_trading.tradingorder")),
        ]),
        migrations.CreateModel(name="ExecutionQualityReport", fields=[
            ("report_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("reference_price", models.DecimalField(decimal_places=18, max_digits=36)), ("execution_price", models.DecimalField(decimal_places=18, max_digits=36)),
            ("filled_quantity", models.DecimalField(decimal_places=18, max_digits=36)), ("slippage_bps", models.DecimalField(decimal_places=8, max_digits=24)),
            ("price_improvement_amount", models.DecimalField(decimal_places=18, max_digits=36)), ("price_improvement_bps", models.DecimalField(decimal_places=8, max_digits=24)),
            ("measurement_version", models.CharField(max_length=32)), ("evidence_hash", models.CharField(max_length=64)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("order", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="execution_quality", to="canonical_trading.tradingorder")),
            ("routing_decision", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="canonical_trading.executionroutingdecision")),
        ]),
    ]
