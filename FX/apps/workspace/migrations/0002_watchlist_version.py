from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workspace", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="watchlist",
            name="version",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
