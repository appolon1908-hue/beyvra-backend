from rest_framework import serializers

from .models import AssetBalance, RealWallet


class RealWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = RealWallet
        fields = ("id", "status", "created_at")
        read_only_fields = fields


class RealWalletBalanceSerializer(serializers.ModelSerializer):
    asset = serializers.SerializerMethodField()
    network = serializers.SerializerMethodField()
    posted_atomic = serializers.SerializerMethodField()
    pending_credit_atomic = serializers.SerializerMethodField()
    held_atomic = serializers.SerializerMethodField()
    reserved_atomic = serializers.SerializerMethodField()
    available_atomic = serializers.SerializerMethodField()

    class Meta:
        model = AssetBalance
        fields = (
            "id", "asset", "network", "posted_atomic", "pending_credit_atomic",
            "held_atomic", "reserved_atomic", "available_atomic",
        )

    def get_asset(self, obj):
        return {"id": str(obj.asset_network.asset_id), "symbol": obj.asset_network.asset.symbol, "decimals": obj.asset_network.asset.decimals}

    def get_network(self, obj):
        return {"id": str(obj.asset_network.network_id), "code": obj.asset_network.network.code}

    def get_posted_atomic(self, obj):
        return str(obj.posted_atomic)

    def get_pending_credit_atomic(self, obj):
        return str(obj.pending_credit_atomic)

    def get_held_atomic(self, obj):
        return str(obj.held_atomic)

    def get_reserved_atomic(self, obj):
        return str(obj.reserved_atomic)

    def get_available_atomic(self, obj):
        return str(obj.available_atomic)
