from datetime import datetime, timezone
from decimal import Decimal

import requests
from django.conf import settings

from .models import MarketCandle
from provider_governance.service import ProviderNotAvailable, resolve_provider

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
        "open": str(candle.open),
        "high": str(candle.high),
        "low": str(candle.low),
        "close": str(candle.close),
        "volume": str(candle.volume),
    }


def get_market_history(*, symbol: str, interval: str, limit: int, before: int | None = None):
    validate_market(symbol, interval)
    if getattr(settings, "DEMO_MARKET_FIXTURE_ENABLED", False):
        # Explicit staging-only paper-market fixture. It is deterministic,
        # creates no provider call, and cannot be enabled outside staging.
        step = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}[interval]
        end = (before or int(datetime.now(tz=timezone.utc).timestamp())) // step * step
        base = Decimal(100 + sum(symbol.encode("utf-8")) % 1000)
        candles = []
        for index in range(max(1, min(limit, 500))):
            timestamp = end - (max(1, min(limit, 500)) - index) * step
            offset = Decimal((timestamp // step) % 17) / Decimal("10")
            open_price = base + offset
            close_price = open_price + (Decimal("0.10") if index % 2 == 0 else Decimal("-0.10"))
            candles.append({
                "time": timestamp,
                "open": str(open_price),
                "high": str(max(open_price, close_price) + Decimal("0.20")),
                "low": str(min(open_price, close_price) - Decimal("0.20")),
                "close": str(close_price),
                "volume": str(Decimal(1000 + index)),
            })
        return candles
    provider_id = "twelve_data" if symbol in TWELVE_DATA_SYMBOLS else "binance"
    try:
        resolved_provider = resolve_provider(
            provider_id=provider_id,
            provider_type="MARKET_DATA",
            product="HISTORICAL_CANDLES",
            symbol=symbol,
            region="GLOBAL",
        )
    except ProviderNotAvailable as exc:
        raise MarketDataError("PROVIDER_NOT_AVAILABLE") from exc
    if symbol in TWELVE_DATA_SYMBOLS:
        return get_twelve_data_history(
            symbol=symbol,
            interval=interval,
            limit=limit,
            credential_path=resolved_provider.credential_path,
            before=before,
        )
    try:
        provider_response = requests.get(
            BINANCE_REST_URL,
            params={"symbol": symbol, "interval": interval, "limit": limit, **({"endTime": before * 1000 - 1} if before else {})},
            timeout=10,
        )
        provider_response.raise_for_status()
        rows = provider_response.json()
    except (requests.RequestException, ValueError) as exc:
        cached_query = MarketCandle.objects.filter(symbol=symbol, interval=interval)
        if before:
            cached_query = cached_query.filter(timestamp__lt=datetime.fromtimestamp(before, tz=timezone.utc))
        cached = list(cached_query.order_by("-timestamp")[:limit])
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


def get_twelve_data_history(*, symbol: str, interval: str, limit: int, credential_path: str, before: int | None = None):
    try:
        with open(credential_path, encoding="utf-8") as credential_file:
            api_key = credential_file.read().strip()
    except OSError as exc:
        raise MarketDataError("PROVIDER_NOT_AVAILABLE") from exc
    if not api_key:
        raise MarketDataError("PROVIDER_NOT_AVAILABLE")
    try:
        provider_response = requests.get(
            getattr(settings, "TWELVE_DATA_REST_URL", "https://api.twelvedata.com/time_series"),
            params={
                "symbol": symbol,
                "interval": TWELVE_INTERVALS[interval],
                "outputsize": limit,
                "timezone": "UTC",
                **({"end_date": datetime.fromtimestamp(before, tz=timezone.utc).isoformat()} if before else {}),
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
        cached_query = MarketCandle.objects.filter(provider="twelve_data", symbol=symbol, interval=interval)
        if before:
            cached_query = cached_query.filter(timestamp__lt=datetime.fromtimestamp(before, tz=timezone.utc))
        cached = list(cached_query.order_by("-timestamp")[:limit])
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
