import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from django.test import SimpleTestCase
from financial_boundary.views import WithdrawalView
from users.models import User


@override_settings(
    REAL_MONEY_ENABLED=False, REAL_WALLET_READ_ENABLED=False, REAL_DEPOSITS_ENABLED=False,
    REAL_WITHDRAWALS_ENABLED=False, REAL_INTERNAL_TRANSFERS_ENABLED=False,
)
class DisabledFinancialApiTests(APITestCase):
    def setUp(self):
        with patch("users.signals.async_send_welcome_email.delay"):
            self.user = User.objects.create_user(email="financial-boundary@example.test", password="strong-pass", phone_number="+12025550142")
        self.client.force_authenticate(self.user)

    def test_all_canonical_routes_fail_closed_without_calling_financial_or_provider(self):
        operation = uuid.uuid4()
        routes = [
            ("get", "/api/v1/wallets/"), ("get", "/api/v1/wallets/USD"),
            ("get", "/api/v1/deposits/"), ("get", f"/api/v1/deposits/{operation}"), ("post", "/api/v1/deposits/"),
            ("get", "/api/v1/withdrawals/"), ("get", f"/api/v1/withdrawals/{operation}"), ("post", "/api/v1/withdrawals/"),
            ("post", f"/api/v1/withdrawals/{operation}/cancel"),
            ("get", "/api/v1/transfers/"), ("get", f"/api/v1/transfers/{operation}"), ("post", "/api/v1/transfers/"),
        ]
        with patch("financial_client.client.FinancialServiceClient", autospec=True) as financial, patch("financial_boundary.providers.DisabledProvider", autospec=True) as provider:
            for method, route in routes:
                response = getattr(self.client, method)(route, {}, format="json")
                self.assertEqual(response.status_code, 503, route)
                self.assertEqual(response.data["code"], "FEATURE_DISABLED")
                self.assertNotIn("request_id", response.data)
            financial.assert_not_called()
            provider.assert_not_called()

    @override_settings(REAL_MONEY_ENABLED=True, REAL_WITHDRAWALS_ENABLED=True)
    def test_single_flags_cannot_activate_mutation(self):
        response = self.client.post("/api/v1/withdrawals/", {"amount": "1.00", "asset": "USD"}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "FEATURE_DISABLED")


@override_settings(REAL_MONEY_ENABLED=False, REAL_WITHDRAWALS_ENABLED=False)
class DisabledConcurrencyTests(SimpleTestCase):
    def test_one_hundred_identical_requests_have_zero_effects(self):
        factory = APIRequestFactory()
        actor = SimpleNamespace(is_authenticated=True)
        def request_once(_):
            request = factory.post("/api/v1/withdrawals/", {"amount": "10.00", "asset": "USD"}, format="json", HTTP_IDEMPOTENCY_KEY="same-key")
            force_authenticate(request, user=actor)
            return WithdrawalView.as_view()(request).data["code"]
        with patch("financial_client.client.FinancialServiceClient", autospec=True) as financial:
            with ThreadPoolExecutor(max_workers=20) as pool:
                results = list(pool.map(request_once, range(100)))
        self.assertEqual(results, ["FEATURE_DISABLED"] * 100)
        financial.assert_not_called()
