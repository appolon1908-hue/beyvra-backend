from datetime import datetime, timezone
from decimal import Decimal

import requests
from django.conf import settings

from .models import MarketCandle

BINANCE_REST_URL = "https://api.binance.com/api/v3/klines"
CRYPTO_SYMBOLS = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}
TWELVE_DATA_SYMBOLS = {"AAPL", "MSFT", "TSLA", "EUR/USD", "GBP/USD", "USD/JPY"}
SUPPORTED_SYMBOLS = CRYPTO_SYMBOLS | TWELVE_DATA_SYMBOLS
SUPPORTED_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}
TWELVE_INTERVALS = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1day"}


class MarketDataError(Exception):
    pass


def validate_market(symbol: str, interval: str):
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"Unsupported symbol: {symbol}")
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Unsupported interval: {interval}")


def serialize_candle(candle: MarketCandle):
    return {
        "time": int(candle.timestamp.timestamp()),
        "open": float(candle.open),
        "high": float(candle.high),
        "low": float(candle.low),
        "close": float(candle.close),
        "volume": float(candle.volume),
    }


def get_market_history(*, symbol: str, interval: str, limit: int):
    validate_market(symbol, interval)
    approval_ready = all(
        (
            getattr(settings, "MARKET_PROVIDER_ENABLED", False),
            getattr(settings, "MARKET_PROVIDER_APPROVAL_REFERENCE", ""),
            getattr(settings, "MARKET_PROVIDER_LICENSE_REFERENCE", ""),
            getattr(settings, "MARKET_PROVIDER_CREDENTIAL_REFERENCE", ""),
        )
    )
    if not approval_ready:
        raise MarketDataError("Market provider activation is pending approval")
    if symbol in TWELVE_DATA_SYMBOLS:
        return get_twelve_data_history(symbol=symbol, interval=interval, limit=limit)
    try:
        provider_response = requests.get(
            BINANCE_REST_URL,
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=10,
        )
        provider_response.raise_for_status()
        rows = provider_response.json()
    except (requests.RequestException, ValueError) as exc:
        cached = list(MarketCandle.objects.filter(symbol=symbol, interval=interval).order_by("-timestamp")[:limit])
        if not cached:
            raise MarketDataError("Market history is temporarily unavailable") from exc
        return [serialize_candle(candle) for candle in reversed(cached)]

    candles = []
    for row in rows:
        timestamp = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc)
        candle, _ = MarketCandle.objects.update_or_create(
            provider="binance",
            symbol=symbol,
            interval=interval,
            timestamp=timestamp,
            defaults={
                "open": Decimal(row[1]), "high": Decimal(row[2]),
                "low": Decimal(row[3]), "close": Decimal(row[4]),
                "volume": Decimal(row[5]),
            },
        )
        candles.append(serialize_candle(candle))
    return candles


def get_twelve_data_history(*, symbol: str, interval: str, limit: int):
    api_key = settings.TWELVE_DATA_API_KEY
    if not api_key:
        raise MarketDataError("Stock and forex market data is not configured")
    try:
        provider_response = requests.get(
            getattr(settings, "TWELVE_DATA_REST_URL", "https://api.twelvedata.com/time_series"),
            params={
                "symbol": symbol,
                "interval": TWELVE_INTERVALS[interval],
                "outputsize": limit,
                "timezone": "UTC",
            },
            headers={"Authorization": f"apikey {api_key}"},
            timeout=10,
        )
        provider_response.raise_for_status()
        payload = provider_response.json()
        if payload.get("status") == "error":
            raise MarketDataError(payload.get("message", "Market provider rejected the request"))
        rows = payload.get("values", [])
    except (requests.RequestException, ValueError) as exc:
        cached = list(
            MarketCandle.objects.filter(provider="twelve_data", symbol=symbol, interval=interval)
            .order_by("-timestamp")[:limit]
        )
        if not cached:
            raise MarketDataError("Stock and forex history is temporarily unavailable") from exc
        return [serialize_candle(candle) for candle in reversed(cached)]

    candles = []
    for row in reversed(rows):
        timestamp = datetime.fromisoformat(row["datetime"]).replace(tzinfo=timezone.utc)
        candle, _ = MarketCandle.objects.update_or_create(
            provider="twelve_data",
            symbol=symbol,
            interval=interval,
            timestamp=timestamp,
            defaults={
                "open": Decimal(row["open"]),
                "high": Decimal(row["high"]),
                "low": Decimal(row["low"]),
                "close": Decimal(row["close"]),
                "volume": Decimal(row.get("volume") or 0),
            },
        )
        candles.append(serialize_candle(candle))
    return candles
