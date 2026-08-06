from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .market_data import SUPPORTED_INTERVALS, SUPPORTED_SYMBOLS, MarketDataError, get_market_history
from .models import MarketCandle


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
