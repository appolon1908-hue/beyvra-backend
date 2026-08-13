from django.utils import timezone
from rest_framework import generics, permissions, response, status, views
from rest_framework_simplejwt.authentication import JWTAuthentication
from .market_data import MarketDataError, get_market_history

from .models import Asset, Trade
from .serializers import AssetSerializer, TradeDetailSerializer


class AssetListView(generics.ListAPIView):
    queryset = Asset.objects.all()
    serializer_class = AssetSerializer
    permission_classes = [permissions.IsAuthenticated]


class TradeListCreateView(generics.ListAPIView):
    """Deprecated read-only projection of historical demo trades."""

    serializer_class = TradeDetailSerializer
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

class TradeDetailView(generics.RetrieveAPIView):
    serializer_class = TradeDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Trade.objects.filter(wallet__user=self.request.user)


class MarketHistoryView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        symbol = request.query_params.get("symbol", "BTCUSDT").upper()
        interval = request.query_params.get("interval", "1m")
        try:
            limit = min(max(int(request.query_params.get("limit", 500)), 1), 1000)
            candles = get_market_history(symbol=symbol, interval=interval, limit=limit)
        except ValueError as exc:
            return response.Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except MarketDataError as exc:
            return response.Response(
                {"error": {"code": "TEMPORARILY_UNAVAILABLE", "message": "Market data is temporarily unavailable.", "details": {}}, "code": "TEMPORARILY_UNAVAILABLE", "message": "Market data is temporarily unavailable.", "details": {}}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        return response.Response({"symbol": symbol, "interval": interval, "results": candles})
