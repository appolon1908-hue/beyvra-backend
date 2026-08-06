from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from trade.models import MarketCandle
from provider_governance.models import ProviderApproval, ProviderDefinition, ProviderLicense


def approve_provider(provider_id, provider_type="MARKET_DATA"):
    provider = ProviderDefinition.objects.create(
        provider_id=provider_id, provider_type=provider_type, enabled=True
    )
    ProviderLicense.objects.create(
        provider=provider,
        environment="STAGING",
        status="APPROVED",
        license_reference=f"license:{provider_id}",
    )
    ProviderApproval.objects.create(
        provider=provider,
        provider_type=provider_type,
        environment="STAGING",
        status="APPROVED",
        approved_by="test-suite",
        approved_at="2026-08-06T00:00:00Z",
        approval_reference=f"approval:{provider_id}",
        license_reference=f"license:{provider_id}",
        credential_reference=f"market/{provider_id}.key",
        allowed_products=["HISTORICAL_CANDLES"],
        allowed_symbols=["*"],
        allowed_regions=["GLOBAL"],
    )
    return provider


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
        "UNAUTHENTICATED_USER": None,
    }
)
class MarketHistoryTests(TestCase):
    def setUp(self):
        # Market-data tests must not require a live Celery broker. This patch
        # is scoped to the test instance and never changes production signals.
        self.welcome_email = patch("users.signals.async_send_welcome_email.delay")
        self.welcome_email.start()
        self.addCleanup(self.welcome_email.stop)
        self.user = get_user_model().objects.create_user(
            email="market@example.com",
            password="test-pass",
            phone_number="+12025550124",
        )
        self.client = APIClient()

    def test_market_history_requires_authentication(self):
        response = self.client.get("/api/trades/market/history/", secure=True)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("trade.market_data.requests.get")
    @override_settings(PROVIDER_CREDENTIAL_ROOT="/tmp/provider-test-credentials")
    def test_market_history_is_normalized_and_persisted(self, get):
        approve_provider("binance")
        self._credential("market/binance.key")
        provider_response = Mock()
        provider_response.raise_for_status.return_value = None
        provider_response.json.return_value = [
            [1700000000000, "100", "110", "90", "105", "12.5"]
        ]
        get.return_value = provider_response
        self.client.force_authenticate(self.user)

        response = self.client.get(
            "/api/trades/market/history/?symbol=BTCUSDT&interval=1m&limit=10",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["close"], 105.0)
        self.assertEqual(MarketCandle.objects.count(), 1)

    def test_unsupported_market_is_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(
            "/api/trades/market/history/?symbol=NOTREAL", secure=True
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("trade.market_data.requests.get")
    def test_market_provider_is_fail_closed_without_approval(self, get):
        self.client.force_authenticate(self.user)
        response = self.client.get(
            "/api/trades/market/history/?symbol=BTCUSDT&interval=1m&limit=10",
            secure=True,
        )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        get.assert_not_called()

    @override_settings(PROVIDER_CREDENTIAL_ROOT="/tmp/provider-test-credentials")
    @patch("trade.market_data.requests.get")
    def test_stock_history_uses_twelve_data_and_is_normalized(self, get):
        approve_provider("twelve_data")
        self._credential("market/twelve_data.key")
        provider_response = Mock()
        provider_response.raise_for_status.return_value = None
        provider_response.json.return_value = {
            "status": "ok",
            "values": [
                {
                    "datetime": "2026-08-01 15:59:00",
                    "open": "210",
                    "high": "212",
                    "low": "209",
                    "close": "211",
                    "volume": "1234",
                }
            ],
        }
        get.return_value = provider_response
        self.client.force_authenticate(self.user)

        response = self.client.get(
            "/api/trades/market/history/?symbol=AAPL&interval=1m&limit=10",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["close"], 211.0)
        candle = MarketCandle.objects.get()
        self.assertEqual(candle.provider, "twelve_data")
        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "apikey test-only"})

    def _credential(self, relative_path):
        from pathlib import Path
        path = Path("/tmp/provider-test-credentials") / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test-only")
        path.chmod(0o600)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
