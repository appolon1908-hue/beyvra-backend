import json
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from ws import v2


class RealtimeV2ContractTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = type("User", (), {"id": 42, "is_authenticated": True, "is_active": True})()

    def test_channel_patterns_are_strict(self):
        self.assertIsNotNone(v2._channel_entry("market.BTCUSDT.candle.1m")[1])
        self.assertIsNone(v2._channel_entry("wallet.balance.42.evil")[1])

    @patch.dict("os.environ", {
        "REALTIME_V2_ENABLED": "true",
        "REALTIME_V2_STAGING_ENABLED": "true",
        "CENTRIFUGO_ENABLED": "true",
        "NATS_JETSTREAM_ENABLED": "true",
        "CENTRIFUGO_PROXY_SECRET": "proxy-secret",
    })
    def test_proxy_allows_market_and_denies_other_account(self):
        request = self.factory.post("/", {"channel": "market.BTCUSDT.quote", "user": "42"}, format="json", HTTP_X_CODESTRA_PROXY_SECRET="proxy-secret")
        self.assertEqual(v2.authorize_subscription(request).status_code, 200)
        request = self.factory.post("/", {"channel": "wallet.balance.99", "user": "42"}, format="json", HTTP_X_CODESTRA_PROXY_SECRET="proxy-secret")
        payload = json.loads(v2.authorize_subscription(request).content)
        self.assertEqual(payload["error"]["code"], 403)
