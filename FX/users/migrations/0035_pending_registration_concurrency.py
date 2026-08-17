from django.db import migrations, models
from django.db.models import Count, Q
from django.utils import timezone


def reconcile_pending_registration_evidence(apps, schema_editor):
    PendingRegistration = apps.get_model("users", "PendingRegistration")
    EmailVerificationChallenge = apps.get_model("users", "EmailVerificationChallenge")
    now = timezone.now()

    # Normalize legacy evidence in place. No registration or challenge is
    # deleted; superseded records remain available for audit.
    for registration in PendingRegistration.objects.all().only("id", "email_normalized").iterator():
        normalized = registration.email_normalized.strip().lower()
        if normalized != registration.email_normalized:
            PendingRegistration.objects.filter(pk=registration.pk).update(email_normalized=normalized)

    expired_ids = list(PendingRegistration.objects.filter(
        status="pending_email_verification",
        expires_at__lte=now,
    ).values_list("pk", flat=True))
    if expired_ids:
        PendingRegistration.objects.filter(pk__in=expired_ids).update(status="expired")
        EmailVerificationChallenge.objects.filter(
            registration_id__in=expired_ids,
            status="active",
        ).update(status="invalidated", invalidated_at=now)

    duplicate_emails = (
        PendingRegistration.objects
        .filter(status="pending_email_verification")
        .values("email_normalized")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    for duplicate in duplicate_emails.iterator():
        registrations = PendingRegistration.objects.filter(
            email_normalized=duplicate["email_normalized"],
            status="pending_email_verification",
        ).order_by("-created_at", "-id")
        keep_id = registrations.values_list("id", flat=True).first()
        superseded_ids = list(registrations.exclude(pk=keep_id).values_list("pk", flat=True))
        if superseded_ids:
            PendingRegistration.objects.filter(pk__in=superseded_ids).update(status="expired")
            EmailVerificationChallenge.objects.filter(
                registration_id__in=superseded_ids,
                status="active",
            ).update(status="invalidated", invalidated_at=now)

    duplicate_challenges = (
        EmailVerificationChallenge.objects
        .filter(status="active", registration__isnull=False)
        .values("registration_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    for duplicate in duplicate_challenges.iterator():
        challenges = EmailVerificationChallenge.objects.filter(
            registration_id=duplicate["registration_id"],
            status="active",
        ).order_by("-created_at", "-id")
        keep_id = challenges.values_list("id", flat=True).first()
        challenges.exclude(pk=keep_id).update(status="invalidated", invalidated_at=now)


class Migration(migrations.Migration):
    dependencies = [("users", "0034_allow_multiple_users_without_phone")]

    operations = [
        migrations.RunPython(reconcile_pending_registration_evidence, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="pendingregistration",
            constraint=models.UniqueConstraint(
                fields=("email_normalized",),
                condition=Q(status="pending_email_verification"),
                name="unique_active_pending_registration_email",
            ),
        ),
        migrations.AddConstraint(
            model_name="emailverificationchallenge",
            constraint=models.UniqueConstraint(
                fields=("registration",),
                condition=Q(status="active", registration__isnull=False),
                name="unique_active_otp_per_registration",
            ),
        ),
    ]
