import json
from unittest.mock import patch

import jwt
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from ws import v2


class RealtimeV2ContractTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = type("User", (), {"id": 42, "is_authenticated": True, "is_active": True})()

    def test_channel_patterns_are_strict(self):
        self.assertIsNotNone(v2._channel_entry("market.BTCUSDT.candle.1m")[1])
        self.assertIsNone(v2._channel_entry("wallet.balance.42.evil")[1])
        self.assertIsNotNone(v2._channel_entry("wallet.updated.v1:42")[1])
        self.assertIsNone(v2._channel_entry("wallet.updated.v1:42.evil")[1])

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

    @patch.dict("os.environ", {
        "REALTIME_V2_ENABLED": "true",
        "REALTIME_V2_STAGING_ENABLED": "true",
        "CENTRIFUGO_ENABLED": "true",
        "NATS_JETSTREAM_ENABLED": "true",
        "CENTRIFUGO_TOKEN_HMAC_SECRET": "test-only-realtime-secret-test-only-realtime-secret",
    })
    @patch("ws.v2._tenant", return_value="00000000-0000-4000-8000-000000000001")
    def test_financial_subscription_identity_is_derived_and_feature_disabled(self, _tenant):
        own = self.factory.post("/", {"channel": "withdrawal.updated.v1:42", "user_id": "99"}, format="json")
        force_authenticate(own, user=self.user)
        response = v2.subscription_token(own)
        self.assertEqual(response.status_code, 503)
        body = json.loads(response.content)
        self.assertEqual(body["code"], "FEATURE_DISABLED")

        notification = self.factory.post("/", {"channel": "notification.42", "user_id": "99"}, format="json")
        force_authenticate(notification, user=self.user)
        notification_body = json.loads(v2.subscription_token(notification).content)
        claims = jwt.decode(
            notification_body["token"], "test-only-realtime-secret-test-only-realtime-secret",
            algorithms=["HS256"], audience="centrifugo-subscription",
        )
        self.assertEqual(claims["sub"], "42")
        self.assertEqual(claims["channel"], "notification.42")

        forged = self.factory.post("/", {"channel": "withdrawal.updated.v1:142"}, format="json")
        force_authenticate(forged, user=self.user)
        self.assertEqual(v2.subscription_token(forged).status_code, 403)

    @patch.dict("os.environ", {
        "REALTIME_V2_ENABLED": "true",
        "REALTIME_V2_STAGING_ENABLED": "true",
        "CENTRIFUGO_ENABLED": "true",
        "NATS_JETSTREAM_ENABLED": "true",
        "CENTRIFUGO_PROXY_SECRET": "proxy-secret",
    })
    def test_proxy_uses_exact_private_owner_not_substring(self):
        request = self.factory.post(
            "/", {"channel": "wallet.updated.v1:142", "user": "42"},
            format="json", HTTP_X_CODESTRA_PROXY_SECRET="proxy-secret",
        )
        payload = json.loads(v2.authorize_subscription(request).content)
        self.assertEqual(payload["error"]["code"], 403)
