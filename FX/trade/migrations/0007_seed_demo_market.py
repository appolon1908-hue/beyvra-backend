from django.db import migrations


DEMO_ASSETS = (
    ("Bitcoin", "BTC", "Cryptocurrency"),
    ("Ethereum", "ETH", "Cryptocurrency"),
    ("Apple", "AAPL", "Stock"),
    ("Tesla", "TSLA", "Stock"),
    ("Gold", "XAU", "Commodity"),
    ("Euro / US Dollar", "EURUSD", "Forex"),
)


def seed_demo_market(apps, schema_editor):
    Asset = apps.get_model("trade", "Asset")
    AssetType = apps.get_model("trade", "AssetType")
    TradeCategory = apps.get_model("trade", "TradeCategory")

    for category in ("fixed", "market"):
        TradeCategory.objects.get_or_create(name=category)

    for name, symbol, asset_type_name in DEMO_ASSETS:
        asset_type, _ = AssetType.objects.get_or_create(name=asset_type_name)
        Asset.objects.get_or_create(
            symbol=symbol,
            defaults={"name": name, "asset_type": asset_type},
        )


def remove_demo_market(apps, schema_editor):
    Asset = apps.get_model("trade", "Asset")
    TradeCategory = apps.get_model("trade", "TradeCategory")
    Asset.objects.filter(symbol__in=[item[1] for item in DEMO_ASSETS]).delete()
    TradeCategory.objects.filter(name__in=("fixed", "market")).delete()


class Migration(migrations.Migration):
    dependencies = [("trade", "0006_trade_close_trade_open_trade_result_time")]
    operations = [migrations.RunPython(seed_demo_market, remove_demo_market)]
