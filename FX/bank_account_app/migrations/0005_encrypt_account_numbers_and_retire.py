from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("bank_account_app", "0004_alter_withdrawalrequest_amount_and_more")]

    operations = [
        migrations.AlterField("bankaccount", "account_number", models.CharField(blank=True, max_length=50, null=True)),
        migrations.AddField("bankaccount", "account_number_ciphertext", models.TextField(blank=True, null=True)),
        migrations.AddField("bankaccount", "account_number_nonce", models.CharField(blank=True, max_length=64, null=True)),
        migrations.AddField("bankaccount", "account_number_key_version", models.CharField(default="v1", max_length=32)),
        migrations.AddField("bankaccount", "account_number_fingerprint", models.CharField(db_index=True, default="", max_length=16)),
        migrations.AddField("bankaccount", "account_number_last_four", models.CharField(default="", max_length=4)),
        migrations.AddField("bankaccount", "routing_number_ciphertext", models.TextField(blank=True, null=True)),
        migrations.AddField("bankaccount", "routing_number_nonce", models.CharField(blank=True, max_length=64, null=True)),
        migrations.AddField("bankaccount", "routing_number_key_version", models.CharField(default="v1", max_length=32)),
        migrations.AddField("bankaccount", "routing_number_last_four", models.CharField(default="", max_length=4)),
        migrations.AddField("bankaccount", "swift_code_ciphertext", models.TextField(blank=True, null=True)),
        migrations.AddField("bankaccount", "swift_code_nonce", models.CharField(blank=True, max_length=64, null=True)),
        migrations.AddField("bankaccount", "swift_code_key_version", models.CharField(default="v1", max_length=32)),
        migrations.AddField("bankaccount", "swift_code_last_four", models.CharField(default="", max_length=4)),
        migrations.AddField("bankaccount", "iban_ciphertext", models.TextField(blank=True, null=True)),
        migrations.AddField("bankaccount", "iban_nonce", models.CharField(blank=True, max_length=64, null=True)),
        migrations.AddField("bankaccount", "iban_key_version", models.CharField(default="v1", max_length=32)),
        migrations.AddField("bankaccount", "iban_last_four", models.CharField(default="", max_length=4)),
        migrations.AddField("bankaccount", "is_active", models.BooleanField(default=True)),
        migrations.AddField("bankaccount", "revoked_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddConstraint(
            "bankaccount",
            models.UniqueConstraint(fields=("user", "account_number_fingerprint"), condition=~Q(account_number_fingerprint=""), name="unique_user_bank_account_fingerprint"),
        ),
    ]
