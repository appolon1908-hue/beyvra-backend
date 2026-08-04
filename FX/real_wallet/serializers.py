from rest_framework import serializers

from .models import RealWallet


class RealWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = RealWallet
        fields = ("id", "status", "created_at")
        read_only_fields = fields
