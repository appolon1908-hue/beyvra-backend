from django.db import migrations, models


def scope_unambiguous_overrides(apps, schema_editor):
    Assignment = apps.get_model("pricing_authority", "AccountPlanAssignment")
    Override = apps.get_model("pricing_authority", "AccountEntitlementOverride")
    account_ids = Override.objects.filter(tenant_ref="").values_list("account_id", flat=True).distinct()
    for account_id in account_ids.iterator():
        tenants = list(Assignment.objects.filter(
            account_id=account_id,
            status="ACTIVE",
            effective_to__isnull=True,
        ).values_list("tenant_ref", flat=True).distinct()[:2])
        if len(tenants) == 1:
            Override.objects.filter(account_id=account_id, tenant_ref="").update(tenant_ref=tenants[0])


def clear_override_scope(apps, schema_editor):
    Override = apps.get_model("pricing_authority", "AccountEntitlementOverride")
    Override.objects.update(tenant_ref="")


class Migration(migrations.Migration):
    dependencies = [("pricing_authority", "0001_initial")]

    operations = [
        migrations.RemoveConstraint(
            model_name="accountplanassignment",
            name="pricing_one_current_assignment",
        ),
        migrations.AddField(
            model_name="accountentitlementoverride",
            name="tenant_ref",
            field=models.CharField(default="", max_length=128),
        ),
        migrations.RunPython(scope_unambiguous_overrides, clear_override_scope),
        migrations.AddConstraint(
            model_name="accountplanassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(effective_to__isnull=True, status="ACTIVE"),
                fields=("account", "tenant_ref"),
                name="pricing_one_current_assignment_per_tenant",
            ),
        ),
        migrations.AddIndex(
            model_name="accountentitlementoverride",
            index=models.Index(
                fields=["account", "tenant_ref", "entitlement", "status"],
                name="pricing_override_lookup",
            ),
        ),
    ]
