import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Asset, AssetBalance, AssetProfitLoss
from .serializers import AssetSerializer
from django.db import models
from drf_spectacular.utils import extend_schema
import logging


logger = logging.getLogger(__name__)


class CryptoMarketDataView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        url = "https://api.polygon.io/v2/aggs/grouped/locale/global/market/crypto/2023-01-09?adjusted=true&apiKey=tYg3o04wAvVaxPnROtNVXEpFOQKoEWI3"
        response = requests.get(url)
        data = response.json()
        return Response(data)
    
class StockMarketDataView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        url = "https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/2023-01-09?adjusted=true&apiKey=tYg3o04wAvVaxPnROtNVXEpFOQKoEWI3"
        response = requests.get(url)
        data = response.json()
        print(data)
        return Response(data)

class AssetView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id, *args, **kwargs):
        user = id
        assets = Asset.objects.filter(user=user)
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
        total_balance = AssetBalance.objects.aggregate(total_balance=models.Sum('current_balance'))['total_balance']
        return Response(total_balance)

class TotalProfitLossView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        total_profit_loss = AssetProfitLoss.objects.aggregate(total_profit_loss=models.Sum('profit_loss'))['total_profit_loss']
        return Response(total_profit_loss)

