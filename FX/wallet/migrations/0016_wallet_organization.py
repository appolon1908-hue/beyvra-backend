from django.db import migrations, models
import django.db.models.deletion


def backfill_wallet_organizations(apps, schema_editor):
    Membership = apps.get_model("integrations", "OrganizationMembership")
    Wallet = apps.get_model("wallet", "Wallet")
    memberships = {}
    for membership in Membership.objects.order_by("id"):
        memberships.setdefault(membership.user_id, membership.organization_id)
    for wallet in Wallet.objects.filter(organization__isnull=True).iterator():
        organization_id = memberships.get(wallet.user_id)
        if organization_id:
            Wallet.objects.filter(pk=wallet.pk).update(organization_id=organization_id)


class Migration(migrations.Migration):
    dependencies = [("wallet", "0015_seed_demo_currency"), ("integrations", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="wallet",
            name="organization",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="wallets", to="integrations.organization"),
        ),
        migrations.RunPython(backfill_wallet_organizations, migrations.RunPython.noop),
    ]
