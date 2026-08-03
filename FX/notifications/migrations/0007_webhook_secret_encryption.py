from django.db import migrations, models


def encrypt_existing(apps, schema_editor):
    from notifications.services import encrypted_webhook_fields
    WebhookSubscription = apps.get_model("notifications", "WebhookSubscription")
    for row in WebhookSubscription.objects.exclude(secret__isnull=True).exclude(secret=""):
        if row.secret_ciphertext:
            continue
        fields = encrypted_webhook_fields(row.secret)
        for name, value in fields.items():
            setattr(row, name, value)
        row.save(update_fields=list(fields))


class Migration(migrations.Migration):
    dependencies = [("notifications", "0006_alter_usernotifications_is_enabled_and_more")]
    operations = [
        migrations.AlterField(model_name="webhooksubscription", name="secret", field=models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField(model_name="webhooksubscription", name="secret_ciphertext", field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name="webhooksubscription", name="secret_nonce", field=models.CharField(blank=True, max_length=64, null=True)),
        migrations.AddField(model_name="webhooksubscription", name="secret_key_version", field=models.CharField(default="v1", max_length=32)),
        migrations.AddField(model_name="webhooksubscription", name="secret_fingerprint", field=models.CharField(default="", max_length=16)),
        migrations.AddField(model_name="webhooksubscription", name="secret_created_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="webhooksubscription", name="secret_rotated_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="webhooksubscription", name="secret_revoked_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.RunPython(encrypt_existing, migrations.RunPython.noop),
    ]
