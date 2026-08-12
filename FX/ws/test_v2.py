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
        self.assertIsNone(v2._channel_entry("simulation.order.sim-42.evil")[1])

    @patch.dict("os.environ", {
        "REALTIME_V2_ENABLED": "true",
        "REALTIME_V2_STAGING_ENABLED": "true",
        "CENTRIFUGO_ENABLED": "true",
        "NATS_JETSTREAM_ENABLED": "true",
        "CENTRIFUGO_PROXY_SECRET": "proxy-secret",
    })
    @patch("ws.v2._owns_demo_account", return_value=False)
    def test_proxy_allows_market_and_denies_other_account(self, owns_account):
        request = self.factory.post("/", {"channel": "market.BTCUSDT.quote", "user": "42"}, format="json", HTTP_X_CODESTRA_PROXY_SECRET="proxy-secret")
        self.assertEqual(v2.authorize_subscription(request).status_code, 200)
        request = self.factory.post("/", {"channel": "simulation.order.sim-99", "user": "42"}, format="json", HTTP_X_CODESTRA_PROXY_SECRET="proxy-secret")
        payload = json.loads(v2.authorize_subscription(request).content)
        self.assertEqual(payload["error"]["code"], 403)
        owns_account.assert_called_once_with("42", "simulation.order.sim-99")

    @patch("ws.v2._owns_demo_account", return_value=True)
    @patch.dict("os.environ", {"CENTRIFUGO_PROXY_SECRET": "proxy-secret"})
    def test_proxy_accepts_server_verified_account_ownership(self, owns_account):
        request = self.factory.post(
            "/", {"channel": "simulation.order.sim-42", "user": "42"}, format="json",
            HTTP_X_BEYVRA_PROXY_SECRET="proxy-secret",
        )
        self.assertEqual(json.loads(v2.authorize_subscription(request).content), {"result": {}})
        self.assertEqual(owns_account.call_count, 2)
        owns_account.assert_called_with("42", "simulation.order.sim-42")

    @patch.dict("os.environ", {"CENTRIFUGO_PROXY_SECRET": "proxy-secret"})
    def test_proxy_prefers_beyvra_header_and_retains_legacy_header(self):
        modern = self.factory.post("/", {"channel": "market.BTCUSDT.quote", "user": "42"}, format="json", HTTP_X_BEYVRA_PROXY_SECRET="proxy-secret", HTTP_X_CODESTRA_PROXY_SECRET="wrong")
        legacy = self.factory.post("/", {"channel": "market.BTCUSDT.quote", "user": "42"}, format="json", HTTP_X_CODESTRA_PROXY_SECRET="proxy-secret")
        self.assertEqual(v2.authorize_subscription(modern).status_code, 200)
        self.assertEqual(v2.authorize_subscription(legacy).status_code, 200)

    @patch.dict("os.environ", {"CENTRIFUGO_PROXY_SECRET": "proxy-secret"})
    def test_proxy_requires_exact_compliance_user_scope(self):
        own = self.factory.post("/", {"channel": "compliance.profile.updated.v1.42", "user": "42"}, format="json", HTTP_X_CODESTRA_PROXY_SECRET="proxy-secret")
        self.assertEqual(v2.authorize_subscription(own).status_code, 200)
        other = self.factory.post("/", {"channel": "compliance.profile.updated.v1.142", "user": "42"}, format="json", HTTP_X_CODESTRA_PROXY_SECRET="proxy-secret")
        self.assertEqual(json.loads(v2.authorize_subscription(other).content)["error"]["code"], 403)
