from django.test import SimpleTestCase
from django.urls import resolve

from trade.market_api import MarketCapabilityUnsupportedView


class FrontendBackendEndpointConnectionTests(SimpleTestCase):
    """Keep every canonical frontend contract connected to a backend handler."""

    def test_canonical_http_routes_resolve(self):
        identifier = "00000000-0000-0000-0000-000000000000"
        paths = (
            "/api/v1/features/",
            "/api/v1/wallets/",
            "/api/v1/wallets/USD/",
            "/api/v1/deposits/",
            f"/api/v1/deposits/{identifier}/",
            "/api/v1/withdrawals/",
            "/api/v1/withdrawals/preview/",
            f"/api/v1/withdrawals/{identifier}/",
            f"/api/v1/withdrawals/{identifier}/cancel/",
            "/api/v1/transfers/",
            "/api/v1/transfers/preview/",
            f"/api/v1/transfers/{identifier}/",
            "/api/v1/compliance/profile/",
            "/api/v1/compliance/requirements/",
            "/api/v1/realtime/v2/connection-token",
            "/api/v1/realtime/v2/subscription-token",
            "/api/v1/market/instruments",
            "/api/v1/market/quotes",
            "/api/v1/market/candles",
            "/api/v1/market/orderbook/BTC-USD",
            "/api/v1/market/status/BTC-USD",
            "/api/v1/trading/orders/preview",
            "/api/v1/trading/orders",
            "/api/v1/trading/trades",
            "/api/v1/trading/positions",
            "/api/v1/trading/accounts",
            "/api/v1/news",
            "/api/v1/integrations/crm/connections",
            "/api/v1/users/imports",
            "/api/wallet/wallets/",
            "/api/wallet/currencies/",
            "/api/payment/methods/",
            "/api/bank_account/",
            "/api/portfolio/total-balance/",
            "/api/portfolio/total-profit-loss/",
            "/api/assets/",
            "/api/get-clock/",
            "/api/v1/demo/wallet",
            "/api/v1/demo/config",
            "/api/v1/demo/trades",
            "/api/v1/demo/wallet/refill",
            "/api/v1/auth/token/",
            "/api/v1/auth/create/",
            "/api/v1/auth/token/logout/",
            "/api/v1/auth/token/refresh/",
            "/api/v1/auth/password_reset/",
            "/api/v1/auth/send_email_verification/",
            "/api/v1/auth/trading_statistics/",
            "/api/v1/auth/websocket_ticket/",
            "/api/v1/auth/generate_mfa_code/",
            "/api/v1/auth/verify_mfa_code/",
            "/api/v1/auth/register",
            "/api/v1/auth/email-verification/verify",
            "/api/v1/auth/providers",
            "/api/v1/auth/google/start",
            "/api/v1/auth/google/credential",
            "/api/v1/session",
            "/api/v1/me/",
            "/api/v1/notifications/notifications/",
            "/api/v1/notifications/toggle_notification/",
            "/api/user/kyc/",
            "/api/user/kycfiles/",
            "/api/portfolio/stock-market-data/",
            "/api/portfolio/crypto-market-data/",
            "/api/market-data/alpaca/",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertIsNotNone(resolve(path).func)

    def test_unsupported_market_routes_do_not_return_status_payloads(self):
        for path in (
            "/api/v1/market/orderbook/BTC-USD",
            "/api/trades/market/orderbook/BTC-USD",
            "/api/trades/market/trades/BTC-USD",
        ):
            with self.subTest(path=path):
                self.assertIs(resolve(path).func.view_class, MarketCapabilityUnsupportedView)
