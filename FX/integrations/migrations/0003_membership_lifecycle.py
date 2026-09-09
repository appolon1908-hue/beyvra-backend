import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("integrations", "0002_credential_encryption")]

    operations = [
        migrations.AddField(
            model_name="organizationmembership",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="organizationmembership",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="organizationmembership",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
