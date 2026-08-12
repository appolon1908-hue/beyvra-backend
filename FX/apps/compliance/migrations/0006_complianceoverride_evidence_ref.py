from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0005_provider_states_and_immutable_decisions")]
    operations = [
        migrations.AddField(
            model_name="complianceoverride",
            name="evidence_ref",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
