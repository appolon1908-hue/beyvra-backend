"""Converge provider policy/news and Polygon OMS registry branches."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("provider_governance", "0003_register_polygon_oms_disabled"),
        ("provider_governance", "0004_register_newsdata_disabled"),
    ]

    operations = []
