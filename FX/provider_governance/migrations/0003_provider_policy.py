from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("provider_governance", "0002_harden_approval_authority")]

    operations = [
        migrations.AddField(model_name="providerdefinition", name="environment", field=models.CharField(choices=[("STAGING", "Staging"), ("PRODUCTION", "Production")], default="STAGING", max_length=16)),
        migrations.AddField(model_name="providerdefinition", name="license_verified", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="providerdefinition", name="security_approved", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="providerdefinition", name="compliance_approved", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="providerdefinition", name="staging_approved", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="providerdefinition", name="production_approved", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="providerdefinition", name="allowed_asset_classes", field=models.JSONField(default=list)),
        migrations.AddField(model_name="providerdefinition", name="allowed_data_types", field=models.JSONField(default=list)),
        migrations.AddField(model_name="providerdefinition", name="max_staleness_ms", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="providerdefinition", name="priority", field=models.PositiveIntegerField(default=100)),
        migrations.AddField(model_name="providerdefinition", name="failover_allowed", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="providerdefinition", name="updated_by", field=models.CharField(default="system", max_length=255)),
        migrations.AddConstraint(model_name="providerdefinition", constraint=models.CheckConstraint(condition=models.Q(production_approved=False) | (models.Q(enabled=True) & models.Q(license_verified=True) & models.Q(security_approved=True) & models.Q(compliance_approved=True) & models.Q(staging_approved=True)), name="provider_production_requires_approvals")),
    ]
