"""Governed CoinGecko REST adapter (disabled until governance resolves it).

The adapter is intentionally crypto market/reference data only.  It does not
implement order, account, portfolio, custody, or ledger operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import requests

from FX.provider_credentials import required_provider_credential


class CoinGeckoError(RuntimeError):
    pass


@dataclass(frozen=True)
class CoinGeckoConfig:
    base_url: str = "https://api.coingecko.com/api/v3/"
    key_header: str = "x-cg-demo-api-key"
    connect_timeout: float = 2.0
    request_timeout: float = 5.0
    max_response_bytes: int = 2_000_000

    def __post_init__(self):
        if self.base_url not in {
            "https://api.coingecko.com/api/v3/",
            "https://pro-api.coingecko.com/api/v3/",
        }:
            raise ValueError("COINGECKO_HOST_NOT_ALLOWED")
        expected = "x-cg-pro-api-key" if self.base_url.startswith("https://pro-") else "x-cg-demo-api-key"
        if self.key_header != expected:
            raise ValueError("COINGECKO_AUTH_MODE_MISMATCH")


class CoinGeckoAdapter:
    provider_id = "coingecko"

    def __init__(self, config: CoinGeckoConfig | None = None, session=None):
        self.config = config or CoinGeckoConfig()
        self.session = session or requests.Session()

    def capabilities(self):
        return {
            "asset_classes": ["CRYPTO"],
            "operations": ["REFERENCE_DATA", "SPOT_PRICE", "MARKET_SUMMARY", "HISTORICAL_CHART"],
            "execution": False,
            "orderbook": False,
            "websocket": "ENTITLEMENT_REQUIRED",
            "5s_bars": False,
        }

    def health(self):
        return self._get("ping")

    def list_instruments(self, *, include_platform=False):
        return self._get("coins/list", params={"include_platform": str(include_platform).lower()})

    def get_markets(self, coin_ids, *, vs_currency="usd", page=1, per_page=100):
        if not coin_ids:
            return []
        return self._get("coins/markets", params={
            "vs_currency": vs_currency,
            "ids": ",".join(coin_ids),
            "page": min(max(int(page), 1), 250),
            "per_page": min(max(int(per_page), 1), 250),
        })

    def get_coin(self, coin_id):
        return self._get(f"coins/{self._segment(coin_id)}", params={"localization": "false"})

    def get_market_chart(self, coin_id, *, vs_currency="usd", days="1", interval=None):
        params = {"vs_currency": vs_currency, "days": str(days)}
        if interval is not None:
            if interval not in {"5m", "hourly", "daily"}:
                raise ValueError("COINGECKO_INTERVAL_UNSUPPORTED")
            params["interval"] = interval
        return self._get(f"coins/{self._segment(coin_id)}/market_chart", params=params)

    @staticmethod
    def _segment(value):
        value = str(value).strip()
        if not value or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in value):
            raise ValueError("INVALID_PROVIDER_IDENTIFIER")
        return value

    def _get(self, path, params=None):
        key = required_provider_credential("COINGECKO_API_KEY")
        response = self.session.get(
            urljoin(self.config.base_url, path),
            params=params or {},
            headers={self.config.key_header: key, "Accept": "application/json"},
            timeout=(self.config.connect_timeout, self.config.request_timeout),
        )
        if int(response.headers.get("Content-Length", "0") or 0) > self.config.max_response_bytes:
            raise CoinGeckoError("PROVIDER_RESPONSE_TOO_LARGE")
        if response.status_code == 429:
            raise CoinGeckoError("PROVIDER_RATE_LIMITED")
        if response.status_code in {401, 403}:
            raise CoinGeckoError("PROVIDER_NOT_AUTHORIZED")
        if response.status_code >= 500:
            raise CoinGeckoError("PROVIDER_UNAVAILABLE")
        if response.status_code >= 400:
            raise CoinGeckoError("PROVIDER_REQUEST_REJECTED")
        try:
            return response.json()
        except ValueError as exc:
            raise CoinGeckoError("MALFORMED_PROVIDER_RESPONSE") from exc

