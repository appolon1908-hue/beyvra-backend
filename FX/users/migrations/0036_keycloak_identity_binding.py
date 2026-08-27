from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("users", "0035_transactional_email_middleware")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="identity_issuer",
            field=models.URLField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="user",
            name="identity_subject",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=~Q(identity_subject=""),
                fields=("identity_issuer", "identity_subject"),
                name="user_identity_issuer_subject_unique",
            ),
        ),
    ]
