from django.db import migrations, models

import users.utils


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0033_remove_stale_verification_fields"),
    ]

    operations = [
        migrations.RunSQL(
            sql="UPDATE users_user SET phone_number = NULL WHERE phone_number = ''",
            reverse_sql=migrations.RunSQL.noop,
        ),
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
    ]
