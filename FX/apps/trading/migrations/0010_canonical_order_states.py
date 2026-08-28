from django.db import migrations, models


CANONICAL_CHOICES = [
    ("DRAFT", "DRAFT"),
    ("PREVIEWED", "PREVIEWED"),
    ("PENDING_SUBMIT", "PENDING_SUBMIT"),
    ("ACKNOWLEDGED", "ACKNOWLEDGED"),
    ("PARTIALLY_FILLED", "PARTIALLY_FILLED"),
    ("FILLED", "FILLED"),
    ("CANCEL_PENDING", "CANCEL_PENDING"),
    ("CANCELED", "CANCELED"),
    ("REJECTED", "REJECTED"),
    ("EXPIRED", "EXPIRED"),
    ("UNKNOWN", "UNKNOWN"),
    ("RECONCILIATION_REQUIRED", "RECONCILIATION_REQUIRED"),
]


def forward_states(apps, schema_editor):
    TradingOrder = apps.get_model("canonical_trading", "TradingOrder")
    TradingOrder.objects.filter(state="PENDING").update(state="PENDING_SUBMIT")
    TradingOrder.objects.filter(state__in=["ACCEPTED", "OPEN"]).update(state="ACKNOWLEDGED")
    TradingOrder.objects.filter(state="CANCELLED").update(state="CANCELED")


def reverse_states(apps, schema_editor):
    TradingOrder = apps.get_model("canonical_trading", "TradingOrder")
    TradingOrder.objects.filter(state="PENDING_SUBMIT").update(state="PENDING")
    TradingOrder.objects.filter(state="ACKNOWLEDGED").update(state="ACCEPTED")
    TradingOrder.objects.filter(state="CANCELED").update(state="CANCELLED")


class Migration(migrations.Migration):
    dependencies = [
        ("canonical_trading", "0009_merge_converged_trading_graph"),
    ]

    operations = [
        migrations.RunPython(forward_states, reverse_states),
        migrations.AlterField(
            model_name="tradingorder",
            name="state",
            field=models.CharField(
                choices=CANONICAL_CHOICES,
                default="PENDING_SUBMIT",
                max_length=24,
            ),
        ),
    ]
