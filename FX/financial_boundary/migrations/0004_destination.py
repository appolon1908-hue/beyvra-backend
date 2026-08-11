import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("financial_boundary", "0003_financialprojectioncursor")]
    operations = [
        migrations.CreateModel(
            name="Destination",
            fields=[
                ("destination_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenant_ref", models.UUIDField()),
                ("account_ref", models.UUIDField()),
                ("owner_ref", models.PositiveBigIntegerField()),
                ("type", models.CharField(choices=[("CRYPTO", "Crypto"), ("FIAT", "Fiat")], max_length=12)),
                ("asset", models.CharField(max_length=12)),
                ("network", models.CharField(max_length=32)),
                ("masked_display", models.CharField(max_length=96)),
                ("destination_fingerprint", models.CharField(max_length=64)),
                ("beneficiary_ref", models.UUIDField(blank=True, null=True)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("VERIFIED", "Verified"), ("LOCKED", "Locked"), ("REVOKED", "Revoked")], default="PENDING", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("cooldown_until", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "financial_destinations"},
        ),
        migrations.AddConstraint(
            model_name="destination",
            constraint=models.UniqueConstraint(
                fields=("tenant_ref", "account_ref", "type", "network", "destination_fingerprint"),
                name="financial_destination_scope_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="destination",
            index=models.Index(fields=["tenant_ref", "owner_ref", "status"], name="financial_dest_owner_idx"),
        ),
    ]
