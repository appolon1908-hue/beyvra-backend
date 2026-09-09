from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0037_pending_registration_concurrency")]
    operations = [migrations.AddField(
        model_name="pendingregistration", name="is_decoy",
        field=models.BooleanField(default=False),
    )]
