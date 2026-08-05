from django.test import SimpleTestCase
from django.urls import resolve


class EndpointCatalogRouteTests(SimpleTestCase):
    def test_disabled_value_routes_are_registered(self):
        for path in (
            "/api/v1/withdrawals/quote/",
            "/api/v1/withdrawals/00000000-0000-0000-0000-000000000000/confirm/",
            "/api/v1/transfers/preview/",
            "/api/v1/compliance/profile/",
            "/api/v1/trading/orders/",
            "/api/v1/integrations/webhooks/custody/00000000-0000-0000-0000-000000000000/",
        ):
            self.assertIsNotNone(resolve(path).func)
