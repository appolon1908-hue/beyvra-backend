from datetime import datetime, timezone

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .market_data import SUPPORTED_INTERVALS, SUPPORTED_SYMBOLS, MarketDataError, get_market_history
from .models import MarketCandle


CHART_INTERVALS = ("5s", "10s", "15s", "30s", "1m", "5m", "15m", "1h", "4h", "1d")
INSTRUMENTS = {
    "BTC-USD": {"provider_symbol": "BTCUSDT", "asset_class": "CRYPTO", "price_decimals": 2, "quantity_decimals": 8},
    "ETH-USD": {"provider_symbol": "ETHUSDT", "asset_class": "CRYPTO", "price_decimals": 2, "quantity_decimals": 8},
    "BNB-USD": {"provider_symbol": "BNBUSDT", "asset_class": "CRYPTO", "price_decimals": 2, "quantity_decimals": 8},
    "SOL-USD": {"provider_symbol": "SOLUSDT", "asset_class": "CRYPTO", "price_decimals": 3, "quantity_decimals": 8},
    "XRP-USD": {"provider_symbol": "XRPUSDT", "asset_class": "CRYPTO", "price_decimals": 5, "quantity_decimals": 8},
    "AAPL": {"provider_symbol": "AAPL", "asset_class": "EQUITY", "price_decimals": 2, "quantity_decimals": 6},
    "MSFT": {"provider_symbol": "MSFT", "asset_class": "EQUITY", "price_decimals": 2, "quantity_decimals": 6},
    "TSLA": {"provider_symbol": "TSLA", "asset_class": "EQUITY", "price_decimals": 2, "quantity_decimals": 6},
    "EUR-USD": {"provider_symbol": "EUR/USD", "asset_class": "FOREX", "price_decimals": 5, "quantity_decimals": 2},
    "GBP-USD": {"provider_symbol": "GBP/USD", "asset_class": "FOREX", "price_decimals": 5, "quantity_decimals": 2},
    "USD-JPY": {"provider_symbol": "USD/JPY", "asset_class": "FOREX", "price_decimals": 3, "quantity_decimals": 2},
}


def _instrument(instrument_id):
    normalized = instrument_id.strip().upper()
    definition = INSTRUMENTS.get(normalized)
    if definition is None:
        raise ValueError("INSTRUMENT_NOT_FOUND")
    return normalized, definition


def _chart_request(request):
    instrument_id, definition = _instrument(request.query_params.get("instrument_id", "BTC-USD"))
    interval = request.query_params.get("interval", "1m")
    if interval not in CHART_INTERVALS:
        raise ValueError("INTERVAL_UNSUPPORTED")
    limit = min(max(int(request.query_params.get("limit", 500)), 1), 1000)
    return instrument_id, definition, interval, limit


def _server_time():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _market_status(definition):
    return "OPEN" if definition["asset_class"] == "CRYPTO" else "UNKNOWN"


class MarketSnapshotV1View(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        try:
            instrument_id, definition, interval, limit = _chart_request(request)
            candles = get_market_history(symbol=definition["provider_symbol"], interval=interval, limit=limit)
        except (ValueError, MarketDataError) as exc:
            return Response({"code": "MARKET_DATA_UNAVAILABLE", "detail": str(exc)}, status=503)
        latest = candles[-1] if candles else None
        if latest is None:
            return Response({"code": "MARKET_DATA_UNAVAILABLE", "detail": "No snapshot is currently available."}, status=503)
        sequence = int(latest["time"])
        price = str(latest["close"])
        return Response({
            "instrument_id": instrument_id,
            "interval": interval,
            "sequence": sequence,
            "server_time": _server_time(),
            "market_status": _market_status(definition),
            "quote": {"bid": price, "ask": price, "mid": price, "occurred_at": datetime.fromtimestamp(latest["time"], tz=timezone.utc).isoformat().replace("+00:00", "Z")},
            "candles": candles,
        })


class MarketCandlesV1View(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        try:
            instrument_id, definition, interval, limit = _chart_request(request)
            candles = get_market_history(symbol=definition["provider_symbol"], interval=interval, limit=limit)
        except (ValueError, MarketDataError) as exc:
            return Response({"code": "MARKET_DATA_UNAVAILABLE", "detail": str(exc)}, status=503)
        sequence = int(candles[-1]["time"]) if candles else 0
        return Response({"instrument_id": instrument_id, "interval": interval, "sequence": sequence, "server_time": _server_time(), "candles": candles})


class MarketStatusV1View(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        try:
            instrument_id, definition = _instrument(request.query_params.get("instrument_id", "BTC-USD"))
        except ValueError as exc:
            return Response({"code": str(exc)}, status=404)
        return Response({"instrument_id": instrument_id, "market_status": _market_status(definition), "server_time": _server_time()})


class InstrumentV1View(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request, instrument_id):
        try:
            normalized, definition = _instrument(instrument_id)
        except ValueError as exc:
            return Response({"code": str(exc)}, status=404)
        return Response({"instrument_id": normalized, **definition, "status": "DEMO_ONLY"})


class InstrumentTradingRulesV1View(InstrumentV1View):
    def get(self, request, instrument_id):
        try:
            normalized, definition = _instrument(instrument_id)
        except ValueError as exc:
            return Response({"code": str(exc)}, status=404)
        return Response({
            "instrument_id": normalized,
            "market_status": _market_status(definition),
            "supported_intervals": CHART_INTERVALS,
            "supported_chart_types": ("CANDLESTICK", "HEIKIN_ASHI", "BAR", "LINE", "AREA"),
            "real_trading_enabled": False,
        })


class InstrumentRegistryView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    def get(self, request, symbol=None):
        symbols = [symbol.upper()] if symbol else sorted(SUPPORTED_SYMBOLS)
        return Response({"results": [{"symbol": item, "status": "ENABLED_FOR_DEMO", "source": "configured-provider"} for item in symbols if item in SUPPORTED_SYMBOLS]})


class MarketCandlesView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    def get(self, request):
        symbol = request.query_params.get("symbol", "BTCUSDT").upper()
        timeframe = request.query_params.get("timeframe", request.query_params.get("interval", "1m"))
        try:
            limit = min(max(int(request.query_params.get("limit", 500)), 1), 1000)
            candles = get_market_history(symbol=symbol, interval=timeframe, limit=limit)
        except (ValueError, MarketDataError) as exc:
            return Response({"code": "MARKET_DATA_UNAVAILABLE", "detail": str(exc), "symbol": symbol, "timeframe": timeframe}, status=503)
        return Response({"symbol": symbol, "timeframe": timeframe, "results": candles, "freshness": "provider_or_cache"})


class MarketQuotesView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    def get(self, request):
        symbol = request.query_params.get("symbol", "BTCUSDT").upper()
        candle = MarketCandle.objects.filter(symbol=symbol).order_by("-timestamp").first()
        if candle is None:
            return Response({"code": "MARKET_DATA_UNAVAILABLE", "detail": "No quote is currently available.", "symbol": symbol}, status=503)
        return Response({"symbol": symbol, "bid": str(candle.close), "ask": str(candle.close), "mid": str(candle.close), "last": str(candle.close), "timestamp": candle.timestamp.isoformat(), "source": candle.provider, "sequence": 0})


class MarketStatusView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    def get(self, request, symbol):
        return Response({"symbol": symbol.upper(), "status": "UNSUPPORTED", "delay_status": "UNKNOWN", "source": None})


class MarketCapabilityUnsupportedView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    def get(self, request, symbol):
        return Response({"code": "CAPABILITY_UNSUPPORTED", "detail": "This provider does not expose the requested capability.", "symbol": symbol.upper()}, status=501)


class FeedHealthView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    def get(self, request):
        return Response({"results": [], "status": "DISCONNECTED", "detail": "No live provider is configured in this environment."})
