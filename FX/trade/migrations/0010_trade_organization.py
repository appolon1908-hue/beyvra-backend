from django.db import migrations, models
import django.db.models.deletion


def backfill_trade_organizations(apps, schema_editor):
    Membership = apps.get_model("integrations", "OrganizationMembership")
    Trade = apps.get_model("trade", "Trade")
    memberships = {}
    for membership in Membership.objects.order_by("id"):
        memberships.setdefault(membership.user_id, membership.organization_id)
    for trade in Trade.objects.select_related("wallet").filter(organization__isnull=True).iterator():
        organization_id = getattr(trade.wallet, "organization_id", None) or memberships.get(trade.wallet.user_id)
        if organization_id:
            Trade.objects.filter(pk=trade.pk).update(organization_id=organization_id)


class Migration(migrations.Migration):
    dependencies = [("trade", "0009_trade_closing_price_trade_demo_result_and_more"), ("integrations", "0001_initial"), ("wallet", "0016_wallet_organization")]
    operations = [
        migrations.AddField(
            model_name="trade",
            name="organization",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="trades", to="integrations.organization"),
        ),
        migrations.RunPython(backfill_trade_organizations, migrations.RunPython.noop),
    ]
