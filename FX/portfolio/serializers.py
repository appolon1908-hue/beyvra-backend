from rest_framework import serializers
from .models import Asset, AssetBalance, AssetProfitLoss

class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = '__all__'

class AssetBalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetBalance
        fields = '__all__'

class AssetProfitLossSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetProfitLoss
        fields = '__all__'  