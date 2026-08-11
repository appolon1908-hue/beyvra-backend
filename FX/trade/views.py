from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError

from operations.services import assert_sensitive_mutation_allowed, tenant_for

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

    def perform_create(self, serializer):
        try:
            assert_sensitive_mutation_allowed(
                tenant_id=tenant_for(self.request.user),
                account=self.request.user,
                action="trading",
            )
        except PermissionError as exc:
            raise ValidationError("ACCOUNT_FROZEN") from exc
        serializer.save()
