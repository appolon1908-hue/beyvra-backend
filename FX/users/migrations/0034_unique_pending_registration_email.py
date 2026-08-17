from django.db import migrations, models


def expire_duplicate_pending_registrations(apps, schema_editor):
    PendingRegistration = apps.get_model("users", "PendingRegistration")
    duplicates = (
        PendingRegistration.objects
        .filter(status="pending_email_verification")
        .values("email_normalized")
        .annotate(total=models.Count("id"))
        .filter(total__gt=1)
    )
    for duplicate in duplicates.iterator():
        registrations = PendingRegistration.objects.filter(
            email_normalized=duplicate["email_normalized"],
            status="pending_email_verification",
        ).order_by("-created_at", "-id")
        keep_id = registrations.values_list("id", flat=True).first()
        registrations.exclude(id=keep_id).update(status="expired")


class Migration(migrations.Migration):
    dependencies = [("users", "0033_remove_stale_verification_fields")]

    operations = [
        migrations.RunPython(expire_duplicate_pending_registrations, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="pendingregistration",
            constraint=models.UniqueConstraint(
                fields=("email_normalized",),
                condition=models.Q(status="pending_email_verification"),
                name="unique_pending_registration_email",
            ),
        ),
    ]
