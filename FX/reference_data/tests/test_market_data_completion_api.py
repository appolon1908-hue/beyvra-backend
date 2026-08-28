from django.test import TestCase, override_settings
from rest_framework.test import APIClient

SIMULATION = override_settings(
    DEPLOYMENT_ENV="test",
    SIMULATED_TRADING_ENABLED=True,
    REAL_TRADING_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    REAL_MONEY_ENABLED=False,
    SIMULATED_EXECUTION_PRICES={"BTC-USD": "100.00"},
    SIMULATED_MARKET_DATA_STALE=False,
)

STALE_MARKET = override_settings(
    DEPLOYMENT_ENV="test",
    SIMULATED_TRADING_ENABLED=True,
    REAL_TRADING_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    REAL_MONEY_ENABLED=False,
    SIMULATED_EXECUTION_PRICES={"BTC-USD": "100.00"},
    SIMULATED_MARKET_DATA_STALE=True,
)


@SIMULATION
class MarketDataCompletionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_get_market_snapshot(self):
        res = self.client.get("/api/v1/market/snapshot?symbols=BTC-USD")
        self.assertEqual(res.status_code, 200)
        data = res.json()["results"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["symbol"], "BTC-USD")
        self.assertEqual(data[0]["bid_price"], "100.00")
        self.assertEqual(data[0]["freshness"], "FRESH")

    def test_get_market_candles(self):
        res = self.client.get("/api/v1/market/candles?symbol=BTC-USD&interval=1m")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["symbol"], "BTC-USD")
        self.assertIn("results", data)

    def test_get_market_capabilities(self):
        res = self.client.get("/api/v1/market/capabilities")
        self.assertEqual(res.status_code, 200)
        self.assertIn("supported_intervals", res.json())


class MarketDataStalePriceTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @STALE_MARKET
    def test_stale_market_data_rejection_normalized_error(self):
        res = self.client.get("/api/v1/market/snapshot?symbols=BTC-USD")
        self.assertEqual(res.status_code, 422)
        err = res.json()["error"]
        self.assertEqual(err["code"], "STALE_QUOTE")
        self.assertTrue(err["retryable"])
