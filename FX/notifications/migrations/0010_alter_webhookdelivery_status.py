from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0009_notification_tenant_preferences"),
    ]

    operations = [
        migrations.AlterField(
            model_name="webhookdelivery",
            name="status",
            field=models.CharField(
                choices=[
                    ("P", "Pending"),
                    ("S", "Successful"),
                    ("F", "Failed"),
                    ("D", "Dead letter"),
                ],
                default="P",
                max_length=1,
            ),
        ),
    ]
