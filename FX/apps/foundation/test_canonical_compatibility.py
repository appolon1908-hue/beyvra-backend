from django.test import SimpleTestCase
from django.urls import resolve


class CanonicalCompatibilityContractTests(SimpleTestCase):
    def test_canonical_http_aliases_resolve(self):
        for route in (
            "/api/v1/auth/token/",
            "/api/v1/auth/password_reset/",
            "/api/v1/me/",
            "/api/v1/notifications/notifications/",
            "/api/v1/market/candles",
            "/api/v1/trading/orders",
            "/api/v1/wallets/",
            "/api/v1/realtime/v2/health",
        ):
            with self.subTest(route=route):
                self.assertIsNotNone(resolve(route).func)

    def test_legacy_routes_still_resolve(self):
        for route in ("/api/user/token/", "/api/notification/notifications/"):
            with self.subTest(route=route):
                self.assertIsNotNone(resolve(route).func)
