from datetime import datetime, timezone
from decimal import Decimal

import requests

from .models import MarketCandle

BINANCE_REST_URL = "https://api.binance.com/api/v3/klines"
SUPPORTED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}
SUPPORTED_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}


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
