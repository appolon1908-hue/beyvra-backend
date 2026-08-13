from django.test import SimpleTestCase
from django.urls import resolve
from django.test import override_settings

from apps.foundation.checks import financial_database_isolation


class CanonicalCompatibilityContractTests(SimpleTestCase):
    def test_polygon_oms_and_financial_halts_are_fail_closed(self):
        with override_settings(
            POLYGON_OMS_ENABLED=False,
            POLYGON_OMS_PRODUCTION_ENABLED=False,
            POLYGON_OMS_HALTED=True,
            CROSS_CHAIN_TRANSFERS_ENABLED=False,
            ALL_FINANCIAL_MUTATIONS_HALTED=True,
        ):
            self.assertEqual(financial_database_isolation(), [])

    @override_settings(POLYGON_OMS_HALTED=False)
    def test_polygon_oms_kill_switch_cannot_be_released(self):
        self.assertIn("codestra.E005", {error.id for error in financial_database_isolation()})

    @override_settings(ALL_FINANCIAL_MUTATIONS_HALTED=False)
    def test_global_financial_halt_cannot_be_released(self):
        self.assertIn("codestra.E006", {error.id for error in financial_database_isolation()})

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
