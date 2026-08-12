from django.db import migrations


def register(apps, schema_editor):
    Provider=apps.get_model("provider_governance","ProviderDefinition")
    Provider.objects.get_or_create(provider_id="newsdata",defaults={"provider_type":"NEWS","enabled":False,"environment":"STAGING","license_verified":False,"security_approved":False,"compliance_approved":False,"staging_approved":False,"production_approved":False,"allowed_asset_classes":[],"allowed_data_types":["LATEST","CRYPTO","MARKET","SOURCES","ARCHIVE"],"max_staleness_ms":0,"priority":100,"failover_allowed":False,"updated_by":"migration"})


def unregister(apps, schema_editor):
    apps.get_model("provider_governance","ProviderDefinition").objects.filter(provider_id="newsdata",enabled=False,license_verified=False,security_approved=False,compliance_approved=False,staging_approved=False,production_approved=False).delete()


class Migration(migrations.Migration):
    dependencies=[("provider_governance","0003_provider_policy")]
    operations=[migrations.RunPython(register,unregister)]
