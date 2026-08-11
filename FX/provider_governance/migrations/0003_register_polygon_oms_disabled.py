from django.db import migrations


def register_polygon_oms(apps, _schema_editor):
    provider = apps.get_model("provider_governance", "ProviderDefinition")
    provider.objects.update_or_create(
        provider_id="polygon_oms",
        defaults={
            "provider_type": "FINANCIAL_INFRASTRUCTURE",
            "enabled": False,
        },
    )


def remove_disabled_polygon_oms(apps, _schema_editor):
    provider = apps.get_model("provider_governance", "ProviderDefinition")
    provider.objects.filter(provider_id="polygon_oms", enabled=False).delete()


class Migration(migrations.Migration):
    dependencies = [("provider_governance", "0002_harden_approval_authority")]
    operations = [migrations.RunPython(register_polygon_oms, remove_disabled_polygon_oms)]
