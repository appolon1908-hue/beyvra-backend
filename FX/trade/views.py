from rest_framework import generics, permissions, response, status, views
from .market_data import MarketDataError, get_market_history
from .models import Asset, Trade
from .serializers import AssetSerializer, TradeSerializer


class AssetListView(generics.ListAPIView):
    queryset = Asset.objects.all()
    serializer_class = AssetSerializer
    permission_classes = [permissions.IsAuthenticated]


class TradeListCreateView(generics.ListCreateAPIView):
    serializer_class = TradeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Trade.objects.filter(wallet__user=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


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
