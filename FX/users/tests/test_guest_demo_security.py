from django.test import SimpleTestCase
from django.urls import Resolver404, resolve
from rest_framework.test import APIClient


class RetiredDemoRouteTests(SimpleTestCase):
    def test_demo_and_anonymous_guest_routes_do_not_resolve(self):
        paths = (
            "/api/v1/demo/sessions",
            "/api/v1/demo/config",
            "/api/v1/demo/orders",
            "/api/v1/demo/orders/preview",
            "/api/v1/demo/trades",
            "/api/v1/demo/wallet",
            "/api/v1/demo/wallet/refill",
            "/api/v1/auth/guest-demo/",
            "/api/user/guest-demo/",
        )
        for path in paths:
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)

    def test_refresh_without_credentials_returns_authentication_error(self):
        response = APIClient().post("/api/v1/auth/token/refresh/", {}, format="json")
        self.assertEqual(response.status_code, 401)
