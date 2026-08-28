import json
from unittest.mock import patch

import jwt
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from ws import v2


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class RealtimeV2ContractTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = type("User", (), {"id": 42, "is_authenticated": True, "is_active": True})()

    def test_channel_patterns_are_strict(self):
        self.assertIsNotNone(v2._channel_entry("market.BTCUSDT.candle.1m")[1])
        self.assertIsNone(v2._channel_entry("market.BTCUSDT.tick")[1])
        self.assertIsNone(v2._channel_entry("market.BTCUSDT.orderbook")[1])
        self.assertIsNone(v2._channel_entry("market.BTCUSDT.trades")[1])
        self.assertIsNone(v2._channel_entry("news.BTC-USD")[1])
        self.assertIsNone(v2._channel_entry("news.market")[1])
        self.assertIsNone(v2._channel_entry("news.economic")[1])
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

    @patch("ws.v2._tenant", return_value="tenant-42")
    @patch.dict("os.environ", {
        "REALTIME_V2_ENABLED": "true",
        "REALTIME_V2_STAGING_ENABLED": "true",
        "CENTRIFUGO_ENABLED": "true",
        "NATS_JETSTREAM_ENABLED": "true",
        "CENTRIFUGO_TOKEN_HMAC_SECRET": "token-secret-token-secret-token-secret-1",
    })
    def test_connection_token_is_short_lived_and_purpose_bound(self, _tenant):
        request = self.factory.post("/")
        force_authenticate(request, user=self.user)

        response = v2.connection_token(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        claims = jwt.decode(payload["token"], "token-secret-token-secret-token-secret-1", algorithms=["HS256"], audience="centrifugo")

        self.assertEqual(payload["expires_in"], 60)
        self.assertEqual(claims["sub"], "42")
        self.assertEqual(claims["tenant_id"], "tenant-42")
        self.assertEqual(claims["aud"], "centrifugo")
        self.assertLessEqual(claims["exp"] - claims["iat"], 60)
        self.assertIn("market.{symbol}.quote", claims["allowed_channel_patterns"])
        self.assertNotIn("news.market", claims["allowed_channel_patterns"])
        self.assertNotEqual(set(claims["allowed_channel_patterns"]), set(v2.CHANNEL_REGISTRY))

    @patch("ws.v2._tenant", return_value="tenant-42")
    @patch.dict("os.environ", {
        "REALTIME_V2_ENABLED": "true",
        "REALTIME_V2_STAGING_ENABLED": "true",
        "CENTRIFUGO_ENABLED": "true",
        "NATS_JETSTREAM_ENABLED": "true",
        "CENTRIFUGO_TOKEN_HMAC_SECRET": "token-secret-token-secret-token-secret-1",
    })
    def test_subscription_token_is_channel_bound_and_denies_escalation(self, _tenant):
        request = self.factory.post("/", {"channel": "market.BTCUSDT.quote"}, format="json")
        force_authenticate(request, user=self.user)
        response = v2.subscription_token(request)
        self.assertEqual(response.status_code, 200)
        claims = jwt.decode(json.loads(response.content)["token"], "token-secret-token-secret-token-secret-1", algorithms=["HS256"], audience="centrifugo-subscription")
        self.assertEqual(claims["channel"], "market.BTCUSDT.quote")
        self.assertEqual(claims["channel_pattern"], "market.{symbol}.quote")

        denied = self.factory.post("/", {"channel": "simulation.order.sim-99"}, format="json")
        force_authenticate(denied, user=self.user)
        self.assertEqual(v2.subscription_token(denied).status_code, 403)

    @patch.dict("os.environ", {
        "REALTIME_V2_ENABLED": "true",
        "REALTIME_V2_STAGING_ENABLED": "true",
        "CENTRIFUGO_ENABLED": "true",
        "NATS_JETSTREAM_ENABLED": "true",
        "CENTRIFUGO_TOKEN_HMAC_SECRET": "token-secret-token-secret-token-secret-1",
    })
    def test_subscription_token_rejects_unpublished_news_channels(self):
        request = self.factory.post("/", {"channel": "news.market"}, format="json")
        force_authenticate(request, user=self.user)
        self.assertEqual(v2.subscription_token(request).status_code, 403)

    @patch("ws.v2._tenant", return_value="tenant-42")
    @patch.dict("os.environ", {
        "REALTIME_V2_ENABLED": "true",
        "REALTIME_V2_STAGING_ENABLED": "true",
        "CENTRIFUGO_ENABLED": "true",
        "NATS_JETSTREAM_ENABLED": "true",
        "CENTRIFUGO_TOKEN_HMAC_SECRET": "token-secret-token-secret-token-secret-1",
    })
    def test_subscription_token_enforces_required_permission_for_public_channels(self, _tenant):
        inactive_user = type("User", (), {"id": 42, "is_authenticated": True, "is_active": False})()
        request = self.factory.post("/", {"channel": "market.BTCUSDT.quote"}, format="json")
        force_authenticate(request, user=inactive_user)
        self.assertEqual(v2.subscription_token(request).status_code, 403)
