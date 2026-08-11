from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.compliance.models import ComplianceProfile
from integrations.models import Organization, OrganizationMembership
from users.models import User
from wallet.models import Currency, Wallet


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class CanonicalRouteMatrixTests(TestCase):
    """Auth, contract, and safe-error probes for every launch-required route."""

    def setUp(self):
        self.organization = Organization.objects.create(name="Route Matrix Tenant")
        self.user = User.objects.create_user(
            email="route-matrix@example.test",
            phone_number="+15555551901",
            first_name="Route",
            last_name="Matrix",
            password="A-valid-test-password-42",
        )
        OrganizationMembership.objects.create(user=self.user, organization=self.organization, role="member")
        currency = Currency.objects.create(name="Synthetic Dollar", symbol="SYN", longer_name="Synthetic Dollar")
        self.wallet = Wallet.objects.create(name="Demo", currency=currency, user=self.user, organization=self.organization, balance="10000.00", is_real=False)
        ComplianceProfile.objects.create(user=self.user, organization=self.organization)
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def test_all_authenticated_get_routes_enforce_auth_and_return_contract_response(self):
        routes = {
            "/api/v1/me": {200},
            "/api/v1/account": {200},
            "/api/v1/account/sessions": {200},
            "/api/v1/account/security-events": {200},
            "/api/v1/compliance/profile": {200},
            "/api/v1/compliance/requirements": {200},
            "/api/v1/compliance/restrictions": {200},
            "/api/v1/market/instruments": {200},
            "/api/v1/market/quotes": {200, 503},
            "/api/v1/market/candles": {200, 503},
            "/api/v1/market/trades/BTCUSDT": {200},
            "/api/v1/market/orderbook/BTCUSDT": {200},
            "/api/v1/market/status/BTCUSDT": {200},
            "/api/v1/demo/account": {200},
            "/api/v1/demo/wallets": {200},
            "/api/v1/demo/orders": {200, 405},
            "/api/v1/demo/trades": {200},
            "/api/v1/demo/positions": {200},
            "/api/v1/trading/orders": {200},
            "/api/v1/trading/trades": {200},
            "/api/v1/trading/positions": {200},
            "/api/v1/trading/accounts": {200},
            "/api/v1/trading/fees": {200},
            "/api/v1/wallets": {503},
            "/api/v1/deposits": {503},
            "/api/v1/withdrawals": {503},
            "/api/v1/transfers": {503},
            "/api/v1/notifications": {200},
            "/api/v1/notifications/preferences": {200},
            "/api/v1/support/cases": {200},
            "/api/v1/reports/activity": {200},
            "/api/v1/reports/trades": {200},
            "/api/v1/reports/fees": {200},
            "/api/v1/reports/transactions": {200},
            "/api/v1/reports/statements": {200},
            "/api/v1/privacy/requests": {200},
        }
        anonymous = APIClient()
        for route, allowed in routes.items():
            with self.subTest(route=route, probe="auth"):
                self.assertEqual(anonymous.get(route).status_code, 401)
            with self.subTest(route=route, probe="contract"):
                response = self.client.get(route)
                self.assertIn(response.status_code, allowed)
                self.assertIsInstance(response.json(), dict)

    @patch("users.views.async_send_password_reset_link_email.delay")
    def test_auth_route_contracts_and_safe_failures(self, delayed_email):
        public = APIClient()
        login = public.post("/api/v1/auth/login", {"email": self.user.email, "password": "A-valid-test-password-42"}, format="json")
        self.assertEqual(login.status_code, 200)
        self.assertIn("access", login.json())
        self.assertEqual(self.client.get("/api/v1/account/sessions").json()["results"][0]["device_label"], "Unknown")
        forgot = public.post("/api/v1/auth/password/forgot", {"email": self.user.email}, format="json")
        self.assertEqual(forgot.status_code, 200)
        delayed_email.assert_called_once()
        self.assertEqual(public.post("/api/v1/auth/password/reset", {"uid": "bad", "token": "bad", "new_password": "Another-valid-password-42", "new_password_confirm": "Another-valid-password-42"}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/v1/auth/mfa/setup").status_code, 200)
        self.assertEqual(public.post("/api/v1/auth/mfa/verify", {"otp": "000000"}, format="json").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/mfa/disable", {"password": "wrong"}, format="json").status_code, 400)
        logout = self.client.post("/api/v1/auth/logout", {"refresh": login.json()["refresh"]}, format="json")
        self.assertEqual(logout.status_code, 200)

    def test_mutation_routes_validate_idempotency_or_fail_closed(self):
        probes = [
            ("/api/v1/compliance/kyc/sessions", {}, 503, "PROVIDER_NOT_AVAILABLE"),
            ("/api/v1/demo/wallets/refill", {}, 400, "IDEMPOTENCY_KEY_REQUIRED"),
            ("/api/v1/trading/orders/preview", {}, 503, "FEATURE_DISABLED"),
            ("/api/v1/trading/orders", {}, 503, "FEATURE_DISABLED"),
            ("/api/v1/withdrawals/preview", {}, 503, "FEATURE_DISABLED"),
            ("/api/v1/withdrawals", {}, 503, "FEATURE_DISABLED"),
            ("/api/v1/transfers/preview", {}, 503, "FEATURE_DISABLED"),
            ("/api/v1/transfers", {}, 503, "FEATURE_DISABLED"),
            ("/api/v1/support/cases", {}, 400, "VALIDATION_ERROR"),
            ("/api/v1/reports/exports", {}, 400, "VALIDATION_ERROR"),
            ("/api/v1/privacy/exports", {}, 400, "IDEMPOTENCY_KEY_REQUIRED"),
            ("/api/v1/privacy/deletion-requests", {}, 400, "IDEMPOTENCY_KEY_REQUIRED"),
            ("/api/v1/operator/actions", {}, 403, "PERMISSION_DENIED"),
        ]
        for route, body, status, code in probes:
            with self.subTest(route=route):
                response = self.client.post(route, body, format="json")
                self.assertEqual(response.status_code, status)
                payload = response.json()
                actual = payload.get("error", payload).get("code")
                self.assertEqual(actual, code)

    def test_public_health_status_and_features_are_bounded(self):
        public = APIClient()
        for route in ("/health/live", "/health/ready", "/api/v1/status", "/api/v1/features"):
            response = public.get(route)
            self.assertEqual(response.status_code, 200, route)
            body = response.json()
            self.assertNotIn("hostname", body)
            self.assertNotIn("database", body)
