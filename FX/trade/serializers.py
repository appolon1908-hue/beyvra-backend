from datetime import datetime, timedelta

from rest_framework import serializers
from wallet.models import Transaction

from .models import Asset, Trade, TradeCategory


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class TransactionCompactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ["transaction_id", "amount"]


class AssetCompactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ["name", "symbol"]


class TradeSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(queryset=TradeCategory.objects.all(), slug_field="name")

    class Meta:
        model = Trade
        fields = "__all__"
        read_only_fields = [
            "id",
            "is_active",
            "transaction",
            "net",
            "result_time",
            "created_at",
            "updated_at",
        ]

    def validate(self, data):
        if data["quantity"] <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        if data["price_per_unit"] <= 0:
            raise serializers.ValidationError("Price per unit must be greater than zero.")
        return data

    def create(self, validated_data):
        wallet = validated_data["wallet"]
        amount = validated_data["price_per_unit"] * validated_data["quantity"]
        duration = validated_data.get("duration", 0)
        # update result time
        validated_data["result_time"] = datetime.now() + timedelta(seconds=duration)
        # Make sure the wallet has enough balance
        if wallet.balance < amount:
            raise serializers.ValidationError("Insufficient balance. please recharge your wallet first.")
        # Create transaction
        transaction = Transaction.objects.create(
            wallet=wallet,
            type="TD",
            amount=(0 - amount),
            status="S",
        )
        # Deduct amount from wallet balance
        wallet.balance -= amount
        wallet.save()
        validated_data["transaction"] = transaction
        return super().create(validated_data)


class TradeDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trade
        fields = [
            "id",
            "wallet",
            "asset",
            "quantity",
            "price_per_unit",
            "trade_type",
            "transaction",
            "category",
            "duration",
            "result_time",
            "net",
            "open",
            "close",
            "is_active",
            "created_at",
            "updated_at",
        ]


class TradeHistorySerializer(serializers.ModelSerializer):
    asset = AssetCompactSerializer()
    transaction = TransactionCompactSerializer()

    class Meta:
        model = Trade
        fields = [
            "id",
            "asset",
            "quantity",
            "trade_type",
            "transaction",
            "duration",
            "open",
            "close",
            "percentage_change",
            "result_time",
            "created_at",
        ]


class TransactionSerializer(serializers.ModelSerializer):
    wallet = serializers.SlugRelatedField(slug_field="name", read_only=True)
    type = serializers.CharField(source="get_type_display", read_only=True)
    status = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Transaction
        fields = "__all__"
        read_only_fields = [
            "id",
            "status",
            "type",
            "amount",
            "created_at",
            "updated_at",
        ]
