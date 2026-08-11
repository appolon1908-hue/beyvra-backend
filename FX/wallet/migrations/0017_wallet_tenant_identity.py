from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("wallet", "0016_wallet_organization")]
    operations = [
        migrations.AlterUniqueTogether(
            name="wallet",
            unique_together={("user", "organization", "name")},
        ),
    ]
