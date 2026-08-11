from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


def encrypt_existing(apps, schema_editor):
    """Migrate legacy Fernet values without ever writing plaintext back."""
    from integrations.crypto import decrypt_secret, encrypt_secret, fingerprint
    CRMConnection = apps.get_model("integrations", "CRMConnection")
    for row in CRMConnection.objects.exclude(secret_encrypted__isnull=True).exclude(secret_encrypted=""):
        if row.secret_ciphertext:
            continue
        value = decrypt_secret(row.secret_encrypted)
        if not value:
            continue
        ciphertext, nonce, version = encrypt_secret(value)
        row.secret_ciphertext = ciphertext
        row.secret_nonce = nonce
        row.secret_key_version = version
        row.secret_fingerprint = fingerprint(value)
        row.secret_encrypted = None
        row.save(update_fields=["secret_ciphertext", "secret_nonce", "secret_key_version", "secret_fingerprint", "secret_encrypted"])


class Migration(migrations.Migration):
    dependencies = [("integrations", "0001_initial")]
    operations = [
        migrations.AddField(model_name="servicetoken", name="environment", field=models.CharField(default="staging", max_length=32)),
        migrations.AddField(model_name="servicetoken", name="fingerprint", field=models.CharField(default="", max_length=16)),
        migrations.AddField(model_name="servicetoken", name="last_four", field=models.CharField(default="", max_length=4)),
        migrations.AddField(model_name="servicetoken", name="last_used_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="servicetoken", name="revoked_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="servicetoken", name="owner", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="issued_service_tokens", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="crmconnection", name="secret_ciphertext", field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name="crmconnection", name="secret_nonce", field=models.CharField(blank=True, max_length=64, null=True)),
        migrations.AddField(model_name="crmconnection", name="secret_key_version", field=models.CharField(default="v1", max_length=32)),
        migrations.AddField(model_name="crmconnection", name="secret_fingerprint", field=models.CharField(default="", max_length=16)),
        migrations.AddField(model_name="crmconnection", name="secret_created_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="crmconnection", name="secret_rotated_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="crmconnection", name="secret_revoked_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AlterField(model_name="crmconnection", name="secret_encrypted", field=models.TextField(blank=True, null=True)),
        migrations.RunPython(encrypt_existing, migrations.RunPython.noop),
    ]
