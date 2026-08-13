import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from FX.settings import _provider_credential
from FX.provider_credentials import ProviderCredentialMissing, required_provider_credential
from wsnotifications.service import UserNotificationService


class ProviderCredentialTests(SimpleTestCase):
    def test_secret_file_reference_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            secret_file = Path(directory) / "provider-secret"
            secret_file.write_text("certification-placeholder\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"POLYGON_API_KEY": "", "POLYGON_API_KEY_FILE": str(secret_file)},
            ):
                self.assertEqual(
                    _provider_credential("POLYGON_API_KEY"),
                    "certification-placeholder",
                )

    def test_multiple_credential_sources_fail_closed(self):
        with patch.dict(
            os.environ,
            {
                "POLYGON_API_KEY": "certification-placeholder",
                "POLYGON_API_KEY_FILE": "/run/secrets/polygon",
            },
        ):
            with self.assertRaisesRegex(ImproperlyConfigured, "only one source"):
                _provider_credential("POLYGON_API_KEY")

    @override_settings(POLYGON_API_KEY="")
    def test_missing_provider_credential_fails_closed(self):
        with self.assertRaisesRegex(ProviderCredentialMissing, "PROVIDER_CREDENTIAL_MISSING"):
            required_provider_credential("POLYGON_API_KEY")

    @override_settings(POLYGON_API_KEY="certification-placeholder")
    def test_present_provider_credential_is_returned(self):
        self.assertEqual(
            required_provider_credential("POLYGON_API_KEY"),
            "certification-placeholder",
        )

    @override_settings(COINGECKO_API_KEY="")
    @patch("wsnotifications.service.requests.get")
    def test_missing_coingecko_credential_prevents_network_request(self, request_get):
        with self.assertRaises(ProviderCredentialMissing):
            UserNotificationService.make_request("https://example.invalid")
        request_get.assert_not_called()

    @override_settings(COINGECKO_API_KEY="certification-placeholder")
    @patch("wsnotifications.service.requests.get")
    def test_coingecko_credential_is_sent_only_as_header(self, request_get):
        request_get.return_value = Mock(status_code=200)
        UserNotificationService.make_request("https://example.invalid")
        request_get.assert_called_once_with(
            "https://example.invalid",
            headers={
                "accept": "application/json",
                "x-cg-demo-api-key": "certification-placeholder",
            },
        )
