import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("canonical_trading", "0001_initial")]
    operations = [
        migrations.AddField(model_name="tradingorder", name="filled_quantity", field=models.DecimalField(decimal_places=18, default=0, max_digits=36)),
        migrations.AddField(model_name="tradingorder", name="average_fill_price", field=models.DecimalField(decimal_places=18, max_digits=36, null=True)),
        migrations.AddField(model_name="tradingorder", name="risk_decision_id", field=models.UUIDField(null=True)),
        migrations.AddField(model_name="tradingorder", name="reservation_id", field=models.UUIDField(null=True)),
        migrations.AddField(model_name="tradingorder", name="simulation", field=models.BooleanField(default=False)),
        migrations.CreateModel(name="SimulatedAccount", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("tenant_ref", models.CharField(max_length=128)), ("subject_ref", models.CharField(max_length=128)), ("account_ref", models.CharField(max_length=128)),
            ("status", models.CharField(default="ACTIVE", max_length=16)), ("quote_currency", models.CharField(default="USD", max_length=16)),
            ("total_balance", models.DecimalField(decimal_places=18, default=10000, max_digits=36)), ("pending_balance", models.DecimalField(decimal_places=18, default=0, max_digits=36)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ], options={"constraints": [models.UniqueConstraint(fields=("tenant_ref", "subject_ref", "account_ref"), name="simulation_account_scope_unique")]}),
        migrations.CreateModel(name="SimulatedReservation", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("order_id", models.UUIDField(unique=True)),
            ("asset", models.CharField(max_length=32)), ("original_amount", models.DecimalField(decimal_places=18, max_digits=36)), ("remaining_amount", models.DecimalField(decimal_places=18, max_digits=36)),
            ("state", models.CharField(choices=[("ACTIVE", "Active"), ("RELEASED", "Released"), ("CONSUMED", "Consumed")], default="ACTIVE", max_length=16)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reservations", to="canonical_trading.simulatedaccount")),
        ]),
        migrations.CreateModel(name="SimulatedPosition", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("instrument_id", models.CharField(max_length=64)),
            ("quantity", models.DecimalField(decimal_places=18, default=0, max_digits=36)), ("average_price", models.DecimalField(decimal_places=18, default=0, max_digits=36)), ("realized_pnl", models.DecimalField(decimal_places=18, default=0, max_digits=36)),
            ("updated_at", models.DateTimeField(auto_now=True)), ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="positions", to="canonical_trading.simulatedaccount")),
        ], options={"constraints": [models.UniqueConstraint(fields=("account", "instrument_id"), name="simulation_position_unique")]}),
        migrations.CreateModel(name="SimulatedTrade", fields=[
            ("trade_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("execution_id", models.CharField(max_length=128, unique=True)),
            ("instrument_id", models.CharField(max_length=64)), ("side", models.CharField(max_length=8)), ("quantity", models.DecimalField(decimal_places=18, max_digits=36)),
            ("price", models.DecimalField(decimal_places=18, max_digits=36)), ("fee", models.DecimalField(decimal_places=18, max_digits=36)), ("executed_at", models.DateTimeField()), ("simulation", models.BooleanField(default=True)),
            ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="simulated_trades", to="canonical_trading.tradingorder")),
        ]),
    ]
