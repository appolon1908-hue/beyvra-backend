from datetime import datetime, timezone

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .market_data import SUPPORTED_INTERVALS, SUPPORTED_SYMBOLS, MarketDataError, get_market_history
from .models import CanonicalMarketStatus, CanonicalQuote, CanonicalTradeTick, MarketCandle
from .market_authority import FIVE_SECOND_AVAILABLE, TIMEFRAME_AUTHORITY, FreshnessState, assess_freshness


CHART_INTERVALS = ("5s", "10s", "15s", "30s", "1m", "5m", "15m", "1h", "4h", "1d")
INTERVAL_SECONDS = {"5s": 5, "10s": 10, "15s": 15, "30s": 30, "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
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
    try:
        from reference_data.models import Instrument as ReferenceInstrument

        canonical = ReferenceInstrument.objects.select_related("venue", "calendar").filter(canonical_symbol=normalized).first()
        if canonical is not None:
            mapping = canonical.provider_mappings.filter(product="MARKET_DATA", effective_to__isnull=True).order_by("provider_id").first()
            if mapping is None:
                raise ValueError("INSTRUMENT_MAPPING_UNAVAILABLE")
            return normalized, {
                "provider_symbol": mapping.provider_symbol,
                "asset_class": canonical.asset_class,
                "price_decimals": max(-canonical.tick_size.as_tuple().exponent, 0),
                "quantity_decimals": max(-canonical.lot_size.as_tuple().exponent, 0),
                "instrument_uuid": str(canonical.instrument_id),
            }
    except (ImportError, RuntimeError):
        # Compatibility during migrations only. Runtime provider identity is
        # authoritative once reference_data is installed.
        pass
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


def _require_available_interval(interval):
    if interval not in SUPPORTED_INTERVALS:
        raise MarketDataError("GENUINE_5S_SOURCE_UNAVAILABLE" if interval == "5s" else "TIMEFRAME_UNAVAILABLE")


def _canonical_candles(candles, interval, instrument_id, before=None):
    duration = INTERVAL_SECONDS[interval]
    normalized = []
    for candle in candles:
        timestamp = int(candle["time"])
        if before is not None and timestamp >= before:
            continue
        open_value = str(candle["open"])
        high_value = str(candle["high"])
        low_value = str(candle["low"])
        close_value = str(candle["close"])
        volume_value = str(candle.get("volume", 0))
        from decimal import Decimal, InvalidOperation
        try:
            o,h,l,c,v = map(Decimal,(open_value,high_value,low_value,close_value,volume_value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise MarketDataError("MALFORMED_PROVIDER_CANDLE") from exc
        if not all(value.is_finite() for value in (o,h,l,c,v)) or min(o,h,l,c) <= 0 or v < 0 or not (h >= max(o,c) and l <= min(o,c) and h >= l):
            raise MarketDataError("MALFORMED_PROVIDER_CANDLE")
        open_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        close_time = datetime.fromtimestamp(timestamp + duration, tz=timezone.utc)
        received_at = candle.get("received_at") or _server_time()
        provider_timestamp = candle.get("provider_timestamp") or open_time.isoformat().replace("+00:00", "Z")
        provider_id = candle.get("provider_id", "UNKNOWN")
        normalized.append({
            "instrument_id": instrument_id, "timeframe": interval,
            "open_time": open_time.isoformat().replace("+00:00", "Z"),
            "close_time": close_time.isoformat().replace("+00:00", "Z"),
            "open": open_value, "high": high_value, "low": low_value,
            "close": close_value, "volume": volume_value,
            "trade_count": candle.get("trade_count"), "provider_id": provider_id,
            "provider_timestamp": provider_timestamp, "received_at": received_at,
            "complete": datetime.now(timezone.utc) >= close_time, "sequence": timestamp,
            "stale": bool(candle.get("stale", False)),
            "provenance": candle.get("provenance") or {"provider_id":provider_id,"provider_message_type":"historical_candle","provider_timestamp":provider_timestamp,"received_at":received_at,"normalizer_version":"1.0.0","source_type":"REST"},
        })
    return normalized


def _server_time():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fresh(record, stale_ms=60000):
    return assess_freshness(record.provider_timestamp,record.received_at,datetime.now(timezone.utc),degraded_ms=stale_ms//2,stale_ms=stale_ms)


def _market_status(definition):
    # A quote, candle, or 24/7 asset class is not market-status authority.
    return "UNKNOWN"


class MarketSnapshotV1View(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        try:
            instrument_id, definition, interval, limit = _chart_request(request)
            _require_available_interval(interval)
            candles = get_market_history(symbol=definition["provider_symbol"], interval=interval, limit=limit)
            candles = _canonical_candles(candles, interval, instrument_id)
        except (ValueError, MarketDataError) as exc:
            return Response({"error": {"code": "TEMPORARILY_UNAVAILABLE", "message": "Market data is temporarily unavailable.", "details": {}}, "code": "TEMPORARILY_UNAVAILABLE", "message": "Market data is temporarily unavailable.", "details": {}}, status=503)
        latest = candles[-1] if candles else None
        if latest is None:
            return Response({"code": "MARKET_DATA_UNAVAILABLE", "detail": "No snapshot is currently available."}, status=503)
        sequence = int(latest["sequence"])
        price = str(latest["close"])
        return Response({
            "instrument_id": instrument_id,
            "interval": interval,
            "sequence": sequence,
            "server_time": _server_time(),
            "market_status": _market_status(definition),
            "quote": None,
            "candles": candles,
        })


class MarketCandlesV1View(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        try:
            instrument_id, definition, interval, limit = _chart_request(request)
            _require_available_interval(interval)
            before_value = request.query_params.get("before")
            before = int(datetime.fromisoformat(before_value.replace("Z", "+00:00")).timestamp()) if before_value else None
            history_kwargs = {"symbol": definition["provider_symbol"], "interval": interval, "limit": limit}
            if before is not None:
                history_kwargs["before"] = before
            candles = get_market_history(**history_kwargs)
            candles = _canonical_candles(candles, interval, instrument_id, before)
        except (ValueError, MarketDataError) as exc:
            return Response({"code": "MARKET_DATA_UNAVAILABLE", "detail": str(exc)}, status=503)
        sequence = int(candles[-1]["sequence"]) if candles else 0
        cursor = candles[0]["open_time"] if candles else None
        return Response({"instrument_id": instrument_id, "interval": interval, "sequence": sequence, "server_time": _server_time(), "history_cursor": cursor, "candles": candles})


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


class InstrumentMarketDataCapabilitiesV1View(InstrumentV1View):
    def get(self, request, instrument_id):
        try:
            normalized, _definition = _instrument(instrument_id)
        except ValueError as exc:
            return Response({"code": str(exc)}, status=404)
        timeframes = []
        for interval in CHART_INTERVALS:
            if interval in SUPPORTED_INTERVALS:
                authority = TIMEFRAME_AUTHORITY[interval]
                timeframes.append({"interval": interval, "available": authority["certified"], "source": authority["source"], "mode": authority["native_or_aggregated"].lower()})
            else:
                reason = "GENUINE_5S_SOURCE_UNAVAILABLE" if interval == "5s" else "TIMEFRAME_SOURCE_UNAVAILABLE"
                timeframes.append({"interval": interval, "available": False, "reason": reason})
        return Response({"instrument_id": normalized, "timeframes": timeframes, "5s_available": FIVE_SECOND_AVAILABLE})


class InstrumentRegistryView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    def get(self, request, symbol=None):
        requested = [symbol.upper()] if symbol else sorted(INSTRUMENTS)
        results=[]
        for instrument_id in requested:
            definition=INSTRUMENTS.get(instrument_id)
            if definition:
                results.append({"instrument_id":instrument_id,"symbol":instrument_id,"display_symbol":instrument_id,"asset_class":definition["asset_class"],"base_asset":instrument_id.split("-")[0],"quote_asset":instrument_id.split("-")[1] if "-" in instrument_id else None,"venue":"UNKNOWN","status":"DEMO_ONLY","price_precision":definition["price_decimals"],"quantity_precision":definition["quantity_decimals"],"timezone":"UTC"})
        return Response({"results":results})


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
        requested=request.query_params.get("instrument_ids") or request.query_params.get("instrument_id") or request.query_params.get("symbol")
        instrument_ids=[item.strip().upper() for item in requested.split(",")] if requested else sorted(INSTRUMENTS)
        results=[]
        for instrument_id in instrument_ids:
            if instrument_id not in INSTRUMENTS: return Response({"code":"INSTRUMENT_NOT_FOUND","instrument_id":instrument_id},status=404)
            quote=CanonicalQuote.objects.filter(instrument_id=instrument_id,suspect=False).order_by("-provider_timestamp").first()
            if quote is None: continue
            freshness=_fresh(quote)
            if freshness in {FreshnessState.STALE,FreshnessState.UNAVAILABLE}: continue
            results.append({"instrument_id":instrument_id,"bid":str(quote.bid) if quote.bid is not None else None,"ask":str(quote.ask) if quote.ask is not None else None,"bid_size":str(quote.bid_size) if quote.bid_size is not None else None,"ask_size":str(quote.ask_size) if quote.ask_size is not None else None,"last":str(quote.last) if quote.last is not None else None,"provider_timestamp":quote.provider_timestamp.isoformat(),"received_at":quote.received_at.isoformat(),"provider_id":quote.provider_id,"sequence":quote.sequence or None,"delayed":quote.delayed,"stale":False,"freshness":freshness.value,"provenance":quote.provenance})
        if not results: return Response({"code":"PROVIDER_NOT_AVAILABLE","detail":"No fresh approved quote authority is available."},status=503)
        return Response({"results":results,"server_time":_server_time()})


class MarketStatusView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    def get(self, request, symbol):
        instrument_id=symbol.upper()
        if instrument_id not in INSTRUMENTS: return Response({"code":"INSTRUMENT_NOT_FOUND"},status=404)
        value=CanonicalMarketStatus.objects.filter(instrument_id=instrument_id).order_by("-provider_timestamp").first()
        if value is None or _fresh(value) in {FreshnessState.STALE,FreshnessState.UNAVAILABLE}: return Response({"instrument_id":instrument_id,"status":"UNKNOWN","halt_status":"UNKNOWN","provider_id":None},status=503)
        return Response({"instrument_id":instrument_id,"status":value.status,"halt_status":value.status if value.halt_status_available else "UNKNOWN","provider_timestamp":value.provider_timestamp.isoformat(),"received_at":value.received_at.isoformat(),"provider_id":value.provider_id,"provenance":value.provenance})


class MarketTradesView(APIView):
    permission_classes=[IsAuthenticated]; authentication_classes=[JWTAuthentication]
    def get(self,request,symbol):
        instrument_id=symbol.upper()
        if instrument_id not in INSTRUMENTS: return Response({"code":"INSTRUMENT_NOT_FOUND"},status=404)
        limit=min(max(int(request.query_params.get("limit",100)),1),1000)
        rows=CanonicalTradeTick.objects.filter(instrument_id=instrument_id).order_by("-provider_timestamp")[:limit]
        results=[{"instrument_id":row.instrument_id,"price":str(row.price),"size":str(row.size),"trade_id":row.trade_id,"provider_timestamp":row.provider_timestamp.isoformat(),"received_at":row.received_at.isoformat(),"provider_id":row.provider_id,"venue":row.venue,"sequence":row.sequence or None,"conditions":row.conditions,"provenance":row.provenance} for row in rows if _fresh(row) not in {FreshnessState.STALE,FreshnessState.UNAVAILABLE}]
        if not results: return Response({"code":"PROVIDER_NOT_AVAILABLE","detail":"No fresh approved trade authority is available."},status=503)
        return Response({"instrument_id":instrument_id,"results":results,"server_time":_server_time()})


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
