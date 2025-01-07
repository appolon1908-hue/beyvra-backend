from rest_framework import generics, permissions

from .models import Asset, Trade
from .serializers import AssetSerializer, TradeSerializer


class AssetListView(generics.ListAPIView):
    queryset = Asset.objects.all()
    serializer_class = AssetSerializer
    permission_classes = [permissions.IsAuthenticated]


class TradeListCreateView(generics.ListCreateAPIView):
    queryset = Trade.objects.all()
    serializer_class = TradeSerializer
    permission_classes = [permissions.IsAuthenticated]
