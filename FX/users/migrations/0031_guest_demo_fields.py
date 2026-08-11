from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0028_user_dob")]

    operations = [
        migrations.AddField(model_name="user", name="is_guest_demo", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="user", name="guest_demo_expires_at", field=models.DateTimeField(blank=True, null=True)),
    ]
