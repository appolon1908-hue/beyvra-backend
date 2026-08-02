from django.db import migrations


def seed_demo_currency(apps, schema_editor):
    Currency = apps.get_model("wallet", "Currency")
    Currency.objects.get_or_create(
        name="Đ",
        defaults={
            "symbol": "DEMO",
            "longer_name": "Demo Dollar",
            "is_crypto": False,
        },
    )


def remove_demo_currency(apps, schema_editor):
    Currency = apps.get_model("wallet", "Currency")
    Currency.objects.filter(name="Đ", symbol="DEMO", longer_name="Demo Dollar").delete()


class Migration(migrations.Migration):
    dependencies = [("wallet", "0014_manualbalanceupdate")]

    operations = [migrations.RunPython(seed_demo_currency, remove_demo_currency)]
