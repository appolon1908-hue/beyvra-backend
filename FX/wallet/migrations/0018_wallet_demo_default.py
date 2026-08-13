from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("wallet", "0017_wallet_tenant_identity")]
    operations = [migrations.AlterField(model_name="wallet", name="is_real", field=models.BooleanField(default=False))]
