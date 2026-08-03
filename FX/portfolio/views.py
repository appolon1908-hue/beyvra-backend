import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Asset, AssetBalance, AssetProfitLoss
from .serializers import AssetSerializer
from django.db import models
from drf_spectacular.utils import extend_schema
import logging
from django.conf import settings
from decimal import Decimal
from wallet.models import Wallet


logger = logging.getLogger(__name__)


class PortfolioSummaryView(APIView):
    """Single authenticated source for dashboard portfolio totals and holdings."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        wallets = Wallet.objects.filter(
            user=request.user, is_archived=False, is_active=True
        ).select_related("currency")
        assets = (
            Asset.objects.filter(user=request.user)
            .select_related("asset_type", "balance", "profit_loss")
            .order_by("name")
        )
        cash_balance = sum((wallet.balance for wallet in wallets), Decimal("0"))
        invested_balance = sum(
            (Decimal(str(asset.balance.current_balance)) for asset in assets if hasattr(asset, "balance")),
            Decimal("0"),
        )
        profit_loss = sum(
            (Decimal(str(asset.profit_loss.profit_loss)) for asset in assets if hasattr(asset, "profit_loss")),
            Decimal("0"),
        )
        distributions = {}
        holdings = []
        for asset in assets:
            asset_type = asset.asset_type.name
            current_balance = Decimal(str(asset.balance.current_balance)) if hasattr(asset, "balance") else Decimal("0")
            distributions[asset_type] = distributions.get(asset_type, Decimal("0")) + current_balance
            holdings.append(
                {
                    "id": asset.id,
                    "name": asset.name,
                    "asset_type": asset_type,
                    "number_of_shares": asset.number_of_shares,
                    "initial_price": asset.initial_price,
                    "current_price": asset.current_price,
                    "current_balance": float(current_balance),
                    "profit_loss": float(asset.profit_loss.profit_loss) if hasattr(asset, "profit_loss") else 0,
                }
            )
        total = cash_balance + invested_balance
        return Response(
            {
                "cash_balance": float(cash_balance),
                "invested_balance": float(invested_balance),
                "total_balance": float(total),
                "profit_loss": float(profit_loss),
                "wallets": [
                    {
                        "id": wallet.id,
                        "name": wallet.name,
                        "balance": float(wallet.balance),
                        "currency": wallet.currency.symbol,
                        "is_real": wallet.is_real,
                    }
                    for wallet in wallets
                ],
                "holdings": holdings,
                "distributions": [
                    {"name": name, "value": float(value), "percentage": float((value / invested_balance * 100) if invested_balance else 0)}
                    for name, value in sorted(distributions.items())
                ],
            }
        )


class CryptoMarketDataView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        url = f"https://api.polygon.io/v2/aggs/grouped/locale/global/market/crypto/2023-01-09?adjusted=true&apiKey={settings.POLYGON_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return Response(data)
    
class StockMarketDataView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        url = f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/2023-01-09?adjusted=true&apiKey={settings.POLYGON_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return Response(data)

class AssetView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id, *args, **kwargs):
        if id != request.user.id:
            return Response({"detail": "Not found."}, status=404)
        assets = Asset.objects.filter(user=request.user)
        serializer = AssetSerializer(assets, many=True)
        return Response(serializer.data)

class CreateAssetView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=AssetSerializer,
        responses={201: AssetSerializer, 400: 'Bad Request'},
    )
    def post(self, request, *args, **kwargs):
        data = request.data
        user = request.user
        asset = Asset(
            user=user,
            name=data.get('name'),
            number_of_shares=data.get('number_of_shares'),
            initial_price=data.get('initial_price'),
            current_price=data.get('current_price'),
            asset_type=data.get('asset_type')
        )
        asset.save()
        AssetBalance.objects.create(asset=asset, current_balance=data.get('current_balance'))
        AssetProfitLoss.objects.create(asset=asset, profit_loss=data.get('profit_loss'))
        serializer = AssetSerializer(asset)
        return Response(serializer.data, status=201)

class TotalBalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        total_balance = AssetBalance.objects.filter(asset__user=request.user).aggregate(total_balance=models.Sum('current_balance'))['total_balance']
        return Response(total_balance)

class TotalProfitLossView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        total_profit_loss = AssetProfitLoss.objects.filter(asset__user=request.user).aggregate(total_profit_loss=models.Sum('profit_loss'))['total_profit_loss']
        return Response(total_profit_loss)
