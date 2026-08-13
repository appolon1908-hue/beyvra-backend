from unittest.mock import Mock

from django.test import SimpleTestCase, override_settings

from trade.coingecko import CoinGeckoAdapter, CoinGeckoConfig, CoinGeckoError


class CoinGeckoAdapterTests(SimpleTestCase):
    def response(self, status=200, payload=None, headers=None):
        value = Mock(status_code=status, headers=headers or {})
        value.json.return_value = {} if payload is None else payload
        return value

    @override_settings(COINGECKO_API_KEY="fixture-key")
    def test_key_is_server_header_and_contract_is_bounded(self):
        session = Mock()
        session.get.return_value = self.response(payload=[{"id": "bitcoin"}])
        result = CoinGeckoAdapter(session=session).get_markets(["bitcoin"], per_page=999)
        self.assertEqual(result, [{"id": "bitcoin"}])
        _url, kwargs = session.get.call_args
        self.assertNotIn("fixture-key", _url)
        self.assertEqual(kwargs["headers"]["x-cg-demo-api-key"], "fixture-key")
        self.assertEqual(kwargs["params"]["per_page"], 250)
        self.assertEqual(kwargs["timeout"], (2.0, 5.0))

    def test_host_and_auth_mode_are_allowlisted(self):
        with self.assertRaisesMessage(ValueError, "COINGECKO_HOST_NOT_ALLOWED"):
            CoinGeckoConfig(base_url="https://example.invalid/api/v3/")
        with self.assertRaisesMessage(ValueError, "COINGECKO_AUTH_MODE_MISMATCH"):
            CoinGeckoConfig(base_url="https://pro-api.coingecko.com/api/v3/")

    @override_settings(COINGECKO_API_KEY="fixture-key")
    def test_safe_error_mapping(self):
        session = Mock()
        session.get.return_value = self.response(status=401)
        with self.assertRaisesMessage(CoinGeckoError, "PROVIDER_NOT_AUTHORIZED"):
            CoinGeckoAdapter(session=session).health()

    def test_capabilities_never_claim_execution_or_fake_depth(self):
        capabilities = CoinGeckoAdapter(session=Mock()).capabilities()
        self.assertFalse(capabilities["execution"])
        self.assertFalse(capabilities["orderbook"])
        self.assertFalse(capabilities["5s_bars"])

