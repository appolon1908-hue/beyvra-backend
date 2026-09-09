from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0011_email_notification_preferences")]
    operations = [
        migrations.AddField(
            model_name="webhookdelivery", name="attempt_limit",
            field=models.PositiveSmallIntegerField(default=5),
        ),
    ]
