from django.db import migrations, models

import users.utils


def normalize_missing_phones(apps, schema_editor):
    user = apps.get_model("users", "User")
    user.objects.filter(phone_number="").update(phone_number=None)


def restore_legacy_missing_phone(apps, schema_editor):
    user = apps.get_model("users", "User")
    missing = user.objects.filter(phone_number__isnull=True)
    if missing.count() > 1:
        raise RuntimeError(
            "Cannot restore the legacy non-null phone constraint after multiple "
            "phone-less identities have been created."
        )
    missing.update(phone_number="")


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0033_remove_stale_verification_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="phone_number",
            field=models.CharField(
                blank=True,
                max_length=16,
                null=True,
                unique=True,
                validators=[users.utils.PHONE_REGEX_VALIDATOR],
            ),
        ),
        migrations.RunPython(normalize_missing_phones, restore_legacy_missing_phone),
    ]
