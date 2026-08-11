from django.test import SimpleTestCase
from django.urls import resolve


class EndpointCatalogRouteTests(SimpleTestCase):
    def test_disabled_value_routes_are_registered(self):
        for path in (
            "/api/v1/legacy-real-wallet/withdrawals/quote/",
            "/api/v1/legacy-real-wallet/withdrawals/00000000-0000-0000-0000-000000000000/confirm/",
            "/api/v1/legacy-real-wallet/transfers/preview/",
            "/api/v1/legacy-real-wallet/compliance/profile/",
            "/api/v1/legacy-real-wallet/trading/orders/",
            "/api/v1/legacy-real-wallet/integrations/webhooks/custody/00000000-0000-0000-0000-000000000000/",
        ):
            self.assertIsNotNone(resolve(path).func)
