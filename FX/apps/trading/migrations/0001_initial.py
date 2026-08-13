import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name="TradingOrder", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("tenant_ref", models.CharField(max_length=128)),
            ("subject_ref", models.CharField(max_length=128)), ("account_ref", models.CharField(max_length=128)), ("instrument_id", models.CharField(max_length=64)),
            ("order_type", models.CharField(choices=[("MARKET", "MARKET"), ("LIMIT", "LIMIT"), ("STOP", "STOP"), ("STOP_LIMIT", "STOP_LIMIT")], max_length=16)), ("side", models.CharField(choices=[("BUY", "BUY"), ("SELL", "SELL")], max_length=8)), ("quantity", models.DecimalField(decimal_places=18, max_digits=36)),
            ("limit_price", models.DecimalField(decimal_places=18, max_digits=36, null=True)), ("stop_price", models.DecimalField(decimal_places=18, max_digits=36, null=True)),
            ("state", models.CharField(choices=[("PENDING", "PENDING"), ("ACCEPTED", "ACCEPTED"), ("OPEN", "OPEN"), ("PARTIALLY_FILLED", "PARTIALLY_FILLED"), ("FILLED", "FILLED"), ("CANCEL_PENDING", "CANCEL_PENDING"), ("CANCELLED", "CANCELLED"), ("REJECTED", "REJECTED"), ("EXPIRED", "EXPIRED")], default="PENDING", max_length=24)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ]),
        migrations.CreateModel(name="RiskDecision", fields=[
            ("decision_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("tenant_ref", models.CharField(max_length=128)),
            ("subject_ref", models.CharField(max_length=128)), ("account_ref", models.CharField(max_length=128)), ("order_id", models.UUIDField(null=True)),
            ("decision", models.CharField(choices=[("ALLOW", "Allow"), ("DENY", "Deny"), ("REVIEW", "Review")], max_length=8)),
            ("reason_codes", models.JSONField(default=list)), ("policy_version", models.CharField(max_length=32)), ("inputs_hash", models.CharField(max_length=64)), ("created_at", models.DateTimeField(auto_now_add=True)),
        ]),
    ]
