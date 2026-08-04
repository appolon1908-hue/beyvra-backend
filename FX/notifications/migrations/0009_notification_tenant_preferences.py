from django.db import migrations, models
import django.db.models.deletion


def backfill_preferences(apps, schema_editor):
    Membership = apps.get_model("integrations", "OrganizationMembership")
    memberships = {}
    for membership in Membership.objects.order_by("id"):
        memberships.setdefault(membership.user_id, membership.organization_id)
    for model_name in ("UserNotifications", "UserAlerts"):
        Model = apps.get_model("notifications", model_name)
        for row in Model.objects.filter(organization__isnull=True).iterator():
            organization_id = memberships.get(row.user_id)
            if organization_id:
                Model.objects.filter(pk=row.pk).update(organization_id=organization_id)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0008_tenant_scope"), ("integrations", "0001_initial")]
    operations = [
        migrations.AddField(model_name="usernotifications", name="organization", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="user_notifications", to="integrations.organization")),
        migrations.AddField(model_name="useralerts", name="organization", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="user_alerts", to="integrations.organization")),
        migrations.RunPython(backfill_preferences, migrations.RunPython.noop),
    ]
