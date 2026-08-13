from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0032_demo_legal_acceptance"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="emailverificationchallenge",
            name="email_challenge_lookup_idx",
        ),
        migrations.RemoveIndex(
            model_name="pendingregistration",
            name="pending_reg_email_status_idx",
        ),
        migrations.RemoveIndex(
            model_name="transactionalemailoutbox",
            name="email_outbox_status_next_idx",
        ),
        migrations.RemoveField(
            model_name="emailverificationchallenge",
            name="user",
        ),
        migrations.AlterField(
            model_name="emailverificationchallenge",
            name="purpose",
            field=models.CharField(default="registration", max_length=32),
        ),
        migrations.AlterField(
            model_name="emailverificationchallenge",
            name="status",
            field=models.CharField(default="active", max_length=16),
        ),
        migrations.AlterField(
            model_name="user",
            name="email_verification_source",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
    ]
