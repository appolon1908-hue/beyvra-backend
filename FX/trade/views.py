from django.db import transaction
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, response, status, views
from .market_data import MarketDataError, get_market_history
from .models import Asset, Trade
from .serializers import AssetSerializer, TradeDetailSerializer, TradeSerializer


class AssetListView(generics.ListAPIView):
    queryset = Asset.objects.all()
    serializer_class = AssetSerializer
    permission_classes = [permissions.IsAuthenticated]


class TradeListCreateView(generics.ListCreateAPIView):
    serializer_class = TradeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Trade.objects.filter(wallet__user=self.request.user).select_related(
            "asset", "wallet", "category", "transaction"
        ).order_by("-created_at")
        trade_status = self.request.query_params.get("status")
        if trade_status == "open":
            queryset = queryset.filter(is_active=True)
        elif trade_status == "completed":
            queryset = queryset.filter(is_active=False)
        elif trade_status == "pending":
            queryset = queryset.filter(is_active=True, result_time__gt=timezone.now())
        return queryset

    def get_serializer_class(self):
        return TradeSerializer if self.request.method == "POST" else TradeDetailSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def create(self, request, *args, **kwargs):
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return super().create(request, *args, **kwargs)
        cache_key = f"trade-idempotency:v2:{request.user.id}:{idempotency_key}"
        cached = cache.get(cache_key)
        if cached and cached != "processing":
            return response.Response(cached["data"], status=cached["status"])
        if not cache.add(cache_key, "processing", timeout=300):
            return response.Response(
                {"detail": "This trade request is already being processed."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            created = super().create(request, *args, **kwargs)
            cache.set(
                cache_key,
                {"data": created.data, "status": created.status_code},
                timeout=300,
            )
            return created
        except Exception:
            cache.delete(cache_key)
            raise


class TradeDetailView(generics.RetrieveAPIView):
    serializer_class = TradeDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Trade.objects.filter(wallet__user=self.request.user)


class TradeCancelView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        with transaction.atomic():
            trade = get_object_or_404(
                Trade.objects.select_for_update().select_related("wallet", "transaction"),
                pk=pk,
                wallet__user=request.user,
            )
            if not trade.is_active:
                return response.Response(
                    {"detail": "Only an open trade can be cancelled."},
                    status=status.HTTP_409_CONFLICT,
                )
            wallet = trade.wallet.__class__.objects.select_for_update().get(pk=trade.wallet_id)
            refund = abs(trade.transaction.amount)
            wallet.balance += refund
            wallet.save(update_fields=["balance", "updated_at"])
            trade.is_active = False
            trade.net = 0
            trade.save(update_fields=["is_active", "net", "updated_at"])
            trade.transaction.status = "R"
            trade.transaction.save(update_fields=["status", "updated_at"])
        return response.Response(TradeDetailSerializer(trade).data)


class MarketHistoryView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        symbol = request.query_params.get("symbol", "BTCUSDT").upper()
        interval = request.query_params.get("interval", "1m")
        try:
            limit = min(max(int(request.query_params.get("limit", 500)), 1), 1000)
            candles = get_market_history(symbol=symbol, interval=interval, limit=limit)
        except (ValueError, MarketDataError) as exc:
            return response.Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return response.Response({"symbol": symbol, "interval": interval, "results": candles})
