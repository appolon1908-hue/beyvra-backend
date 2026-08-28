import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from django.conf import settings
from django.utils import timezone as django_timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.trading.api.errors import error_response


class CanonicalMarketSnapshotView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        symbols_raw = request.query_params.get("symbols", "BTC-USD")
        symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]

        snapshots = []
        now = django_timezone.now()
        for sym in symbols:
            # Check price freshness
            freshness_ms = 120
            if getattr(settings, "SIMULATED_MARKET_DATA_STALE", False):
                return Response({
                    "error": {
                        "code": "STALE_QUOTE",
                        "message": "The market quote is too old to submit this order.",
                        "request_id": getattr(request, "correlation_id", "default_req"),
                        "retryable": True,
                        "details": {
                            "quote_as_of": now.isoformat(),
                            "maximum_age_ms": 1500
                        }
                    }
                }, status=422)

            price = settings.SIMULATED_EXECUTION_PRICES.get(sym, "100.00") if hasattr(settings, "SIMULATED_EXECUTION_PRICES") else "100.00"
            snapshots.append({
                "symbol": sym,
                "source": "SIMULATED_FEED",
                "bid_price": str(price),
                "ask_price": str(price),
                "last_price": str(price),
                "observed_at": now.isoformat(),
                "received_at": now.isoformat(),
                "age_ms": freshness_ms,
                "freshness": "FRESH",
                "quality": "COMPLETE",
                "simulation": True,
                "live_trading_enabled": False
            })
        return Response({"results": snapshots})


class CanonicalMarketCandlesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        symbol = request.query_params.get("symbol", "BTC-USD").upper()
        interval = request.query_params.get("interval", "1m")
        cursor = request.query_params.get("cursor")
        limit = min(int(request.query_params.get("limit", 100)), 500)

        now = django_timezone.now()
        price = settings.SIMULATED_EXECUTION_PRICES.get(symbol, "100.00") if hasattr(settings, "SIMULATED_EXECUTION_PRICES") else "100.00"
        candles = [
            {
                "timestamp": now.isoformat(),
                "open": str(price),
                "high": str(Decimal(price) * Decimal("1.01")),
                "low": str(Decimal(price) * Decimal("0.99")),
                "close": str(price),
                "volume": "100.00000000",
                "source": "SIMULATED_FEED",
                "freshness": "FRESH",
            }
        ]
        return Response({
            "results": candles,
            "symbol": symbol,
            "interval": interval,
            "next_cursor": None,
            "has_more": False
        })


class CanonicalMarketOrderBookView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        symbol = request.query_params.get("symbol", "BTC-USD").upper()
        depth = min(int(request.query_params.get("depth", 20)), 100)
        price = settings.SIMULATED_EXECUTION_PRICES.get(symbol, "100.00") if hasattr(settings, "SIMULATED_EXECUTION_PRICES") else "100.00"

        bids = [[str(Decimal(price) * Decimal("0.999")), "5.00000000"]]
        asks = [[str(Decimal(price) * Decimal("1.001")), "5.00000000"]]

        return Response({
            "symbol": symbol,
            "bids": bids,
            "asks": asks,
            "observed_at": django_timezone.now().isoformat(),
            "freshness": "FRESH",
            "simulation": True,
        })


class CanonicalMarketTradesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        symbol = request.query_params.get("symbol", "BTC-USD").upper()
        price = settings.SIMULATED_EXECUTION_PRICES.get(symbol, "100.00") if hasattr(settings, "SIMULATED_EXECUTION_PRICES") else "100.00"
        return Response({
            "results": [
                {
                    "trade_id": "sim_tr_1",
                    "symbol": symbol,
                    "price": str(price),
                    "quantity": "1.00000000",
                    "side": "BUY",
                    "timestamp": django_timezone.now().isoformat(),
                }
            ],
            "next_cursor": None,
            "has_more": False
        })


class CanonicalMarketCapabilitiesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response({
            "supported_intervals": ["1m", "5m", "15m", "1h", "1d"],
            "realtime_depth": "L2",
            "historical_lookback_days": 1825,
            "simulation": True,
            "live_trading_enabled": False
        })
