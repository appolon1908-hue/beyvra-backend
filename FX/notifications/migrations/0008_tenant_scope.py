from django.db import migrations, models
import django.db.models.deletion


def backfill_organizations(apps, schema_editor):
    OrganizationMembership = apps.get_model("integrations", "OrganizationMembership")
    NotificationEvent = apps.get_model("notifications", "NotificationEvent")
    WebhookSubscription = apps.get_model("notifications", "WebhookSubscription")
    memberships = {}
    for membership in OrganizationMembership.objects.select_related("organization").order_by("id"):
        memberships.setdefault(membership.user_id, membership.organization_id)
    for model in (NotificationEvent, WebhookSubscription):
        for row in model.objects.filter(organization__isnull=True).iterator():
            organization_id = memberships.get(row.user_id)
            if organization_id:
                model.objects.filter(pk=row.pk).update(organization_id=organization_id)


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0007_webhook_secret_encryption"),
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationevent",
            name="organization",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, related_name="notification_events", to="integrations.organization"),
        ),
        migrations.AddField(
            model_name="webhooksubscription",
            name="organization",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, related_name="notification_webhooks", to="integrations.organization"),
        ),
        migrations.RunPython(backfill_organizations, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="webhooksubscription",
            constraint=models.UniqueConstraint(fields=("organization", "url"), name="unique_org_webhook_url"),
        ),
    ]
