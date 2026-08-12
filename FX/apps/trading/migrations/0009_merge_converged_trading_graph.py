"""Converge the simulation and execution-control migration branches."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("canonical_trading", "0002_tradingorder_eligibility_evaluated_at_and_more"),
        ("canonical_trading", "0008_executionqualityreport_revision_and_more"),
    ]

    operations = []
