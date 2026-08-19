import uuid

from django.db import migrations, models


def populate_event_identity(apps, schema_editor):
    Outbox = apps.get_model("users", "TransactionalEmailOutbox")
    for row in Outbox.objects.all().iterator():
        update_fields = []
        if row.notification_id is None:
            row.notification_id = uuid.uuid4()
            update_fields.append("notification_id")
        if not row.event_id:
            row.event_id = f"legacy:{row.id}"
            row.user_id_ref = "pre-migration"
            row.account_id_ref = "pre-migration"
            update_fields.extend(["event_id", "user_id_ref", "account_id_ref"])
        if update_fields:
            row.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [("users", "0034_allow_multiple_users_without_phone")]
    operations = [
        # Add nullable first, populate each row independently, then enforce the
        # production model constraint. This is safe for a non-empty outbox.
        migrations.AddField("transactionalemailoutbox", "notification_id", models.UUIDField(editable=False, null=True)),
        migrations.AddField("transactionalemailoutbox", "event_id", models.CharField(db_index=True, default="", max_length=255)),
        migrations.AddField("transactionalemailoutbox", "correlation_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
        migrations.AddField("transactionalemailoutbox", "user_id_ref", models.CharField(default="", max_length=255)),
        migrations.AddField("transactionalemailoutbox", "account_id_ref", models.CharField(default="", max_length=255)),
        migrations.AddField("transactionalemailoutbox", "tenant_id", models.CharField(db_index=True, default="beyvra", max_length=255)),
        migrations.AddField("transactionalemailoutbox", "provider_status", models.CharField(blank=True, max_length=32)),
        migrations.AddField("transactionalemailoutbox", "lease_expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.RunPython(populate_event_identity, migrations.RunPython.noop),
        migrations.AlterField("transactionalemailoutbox", "notification_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
        migrations.AlterField("transactionalemailoutbox", "event_id", models.CharField(db_index=True, max_length=255)),
        migrations.AlterField("transactionalemailoutbox", "user_id_ref", models.CharField(max_length=255)),
        migrations.AlterField("transactionalemailoutbox", "account_id_ref", models.CharField(max_length=255)),
        migrations.AddIndex("transactionalemailoutbox", models.Index(fields=["status", "next_attempt_at", "lease_expires_at"], name="email_outbox_claim_idx")),
        migrations.AddIndex("transactionalemailoutbox", models.Index(fields=["tenant_id", "created_at"], name="email_outbox_tenant_idx")),
    ]
