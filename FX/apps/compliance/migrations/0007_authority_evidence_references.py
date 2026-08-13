from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0006_complianceoverride_evidence_ref")]
    operations = [
        migrations.RenameField(
            model_name="complianceprofile",
            old_name="provider_reference",
            new_name="kyc_evidence_ref",
        ),
        migrations.AddField(
            model_name="complianceprofile",
            name="aml_evidence_ref",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="complianceprofile",
            name="sanctions_evidence_ref",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
