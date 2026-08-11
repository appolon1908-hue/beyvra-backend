from datetime import timedelta

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone
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
        request = self.context.get("request")
        if request is None or data["wallet"].user_id != request.user.id:
            raise serializers.ValidationError("Wallet does not belong to the authenticated user.")
        if settings.PAPER_TRADING_ONLY and data["wallet"].is_real:
            raise serializers.ValidationError(
                "Real-money trading is disabled in this environment. Select a demo wallet."
            )
        if data["quantity"] <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        if data["price_per_unit"] <= 0:
            raise serializers.ValidationError("Price per unit must be greater than zero.")
        return data

    def create(self, validated_data):
        with db_transaction.atomic():
            wallet = validated_data["wallet"].__class__.objects.select_for_update().get(
                pk=validated_data["wallet"].pk
            )
            amount = validated_data["price_per_unit"] * validated_data["quantity"]
            duration = validated_data.get("duration", 0)
            validated_data["result_time"] = timezone.now() + timedelta(seconds=duration)
            if wallet.balance < amount:
                raise serializers.ValidationError("Insufficient balance. please recharge your wallet first.")
            transaction = Transaction.objects.create(
                wallet=wallet,
                type="TD",
                amount=(0 - amount),
                status="S",
            )
            wallet.balance -= amount
            wallet.save(update_fields=["balance", "updated_at"])
            validated_data["wallet"] = wallet
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
