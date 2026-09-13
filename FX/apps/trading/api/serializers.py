"""Response contracts for the existing account identity and PAPER projection."""

from rest_framework import serializers

from apps.trading.models import TradingAccount


class TradingAccountSerializer(serializers.Serializer):
    account_id = serializers.UUIDField(read_only=True)
    execution_mode = serializers.ChoiceField(
        choices=TradingAccount.ExecutionMode.choices, read_only=True
    )
    base_currency = serializers.CharField(max_length=16, read_only=True)
    status = serializers.ChoiceField(
        choices=TradingAccount.Status.choices, read_only=True
    )
    trading_enabled = serializers.BooleanField(read_only=True)
    funding_enabled = serializers.BooleanField(read_only=True)
    withdrawals_enabled = serializers.BooleanField(read_only=True)


class PaperAccountProjectionSerializer(TradingAccountSerializer):
    """Existing compatibility response; no separate trading account authority."""

    id = serializers.UUIDField(read_only=True)
    account_ref = serializers.CharField(read_only=True)
    currency = serializers.CharField(read_only=True)
    total = serializers.DecimalField(max_digits=36, decimal_places=18, read_only=True)
    available = serializers.DecimalField(
        max_digits=36, decimal_places=18, read_only=True
    )
    reserved = serializers.DecimalField(
        max_digits=36, decimal_places=18, read_only=True
    )
    pending = serializers.DecimalField(max_digits=36, decimal_places=18, read_only=True)
    simulation = serializers.BooleanField(read_only=True)


class AccountCollectionSerializer(serializers.Serializer):
    results = PaperAccountProjectionSerializer(many=True, read_only=True)
