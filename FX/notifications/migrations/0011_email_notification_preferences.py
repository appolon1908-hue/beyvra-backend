from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("notifications", "0010_alter_webhookdelivery_status"), migrations.swappable_dependency(settings.AUTH_USER_MODEL), ("integrations", "0002_credential_encryption")]
    operations = [
        migrations.CreateModel(
            name="EmailNotificationPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("trading", models.BooleanField(default=True)), ("funds", models.BooleanField(default=True)),
                ("statements", models.BooleanField(default=True)), ("support", models.BooleanField(default=True)),
                ("marketing", models.BooleanField(default=False)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="integrations.organization")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="email_notification_preferences", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint("emailnotificationpreference", models.CheckConstraint(condition=models.Q(marketing=False), name="marketing_email_phase1_disabled")),
    ]
