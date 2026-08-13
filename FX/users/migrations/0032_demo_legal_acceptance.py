from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("users", "0030_user_email_verification_source_and_more"), ("users", "0031_guest_demo_fields")]
    operations = [
        migrations.CreateModel(
            name="DemoLegalAcceptance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document_type", models.CharField(max_length=64)),
                ("document_version", models.CharField(max_length=64)),
                ("locale", models.CharField(default="en", max_length=16)),
                ("accepted_at", models.DateTimeField()),
                ("acceptance_source", models.CharField(max_length=64)),
                ("registration_id", models.UUIDField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="demo_legal_acceptances", to="users.user")),
            ],
        ),
    ]
