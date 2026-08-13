from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0006_trade_confirmation_immutable_trigger"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="actor",
            field=models.ForeignKey(
                null=True,
                on_delete=models.PROTECT,
                related_name="operations_audit_events",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
