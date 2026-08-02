from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("trade", "0007_seed_demo_market")]
    operations = [
        migrations.CreateModel(
            name="MarketCandle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(max_length=32)),
                ("interval", models.CharField(default="1m", max_length=8)),
                ("timestamp", models.DateTimeField()),
                ("open", models.DecimalField(decimal_places=10, max_digits=24)),
                ("high", models.DecimalField(decimal_places=10, max_digits=24)),
                ("low", models.DecimalField(decimal_places=10, max_digits=24)),
                ("close", models.DecimalField(decimal_places=10, max_digits=24)),
                ("volume", models.DecimalField(decimal_places=10, default=0, max_digits=30)),
                ("provider", models.CharField(default="binance", max_length=32)),
            ],
            options={"ordering": ["timestamp"]},
        ),
        migrations.AddConstraint(
            model_name="marketcandle",
            constraint=models.UniqueConstraint(fields=("provider", "symbol", "interval", "timestamp"), name="unique_market_candle"),
        ),
        migrations.AddIndex(
            model_name="marketcandle",
            index=models.Index(fields=["symbol", "interval", "-timestamp"], name="trade_marke_symbol_eb9c9d_idx"),
        ),
    ]
