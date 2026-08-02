from rest_framework import generics, permissions

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
