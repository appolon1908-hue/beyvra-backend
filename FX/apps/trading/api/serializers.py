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
    tenant_ref = serializers.CharField(read_only=True)
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


class OrderRequestSerializer(serializers.Serializer):
    instrument = serializers.CharField(max_length=64)
    side = serializers.ChoiceField(choices=("BUY", "SELL"))
    order_type = serializers.ChoiceField(choices=("MARKET", "LIMIT"), default="MARKET")
    quantity = serializers.DecimalField(max_digits=36, decimal_places=18)
    limit_price = serializers.DecimalField(
        max_digits=36,
        decimal_places=18,
        required=False,
    )


class ReplaceOrderRequestSerializer(serializers.Serializer):
    limit_price = serializers.DecimalField(max_digits=36, decimal_places=18)


class ReducePositionRequestSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=36, decimal_places=18)


class PriceEvidenceSerializer(serializers.Serializer):
    observation_id = serializers.UUIDField(allow_null=True)
    source = serializers.CharField()
    observed_at = serializers.DateTimeField(allow_null=True)
    stale_after = serializers.DateTimeField(allow_null=True)


class FeeEvidenceSerializer(serializers.Serializer):
    commission = serializers.DecimalField(max_digits=36, decimal_places=18, required=False)
    spread_cost = serializers.DecimalField(max_digits=36, decimal_places=18, required=False)
    other_fees = serializers.DecimalField(max_digits=36, decimal_places=18, required=False)
    total = serializers.DecimalField(max_digits=36, decimal_places=18)
    currency = serializers.CharField(required=False, allow_null=True)
    schedule_version = serializers.CharField()


class OrderResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    tenant_ref = serializers.CharField()
    account_ref = serializers.CharField()
    instrument = serializers.CharField()
    side = serializers.ChoiceField(choices=("BUY", "SELL"))
    order_type = serializers.ChoiceField(choices=("MARKET", "LIMIT"))
    quantity = serializers.DecimalField(max_digits=36, decimal_places=18)
    limit_price = serializers.DecimalField(max_digits=36, decimal_places=18, allow_null=True)
    reference_price = serializers.DecimalField(max_digits=36, decimal_places=18, allow_null=True)
    filled_quantity = serializers.DecimalField(max_digits=36, decimal_places=18)
    average_fill_price = serializers.DecimalField(max_digits=36, decimal_places=18, allow_null=True)
    state = serializers.CharField()
    version = serializers.IntegerField(min_value=1)
    price_evidence = PriceEvidenceSerializer()
    fees = FeeEvidenceSerializer()
    simulation = serializers.BooleanField()
    eligibility_policy_version = serializers.CharField()
    eligibility_result = serializers.CharField()
    eligibility_reason_codes = serializers.ListField(child=serializers.CharField())
    eligibility_evaluated_at = serializers.DateTimeField(allow_null=True)


class OrderCollectionSerializer(serializers.Serializer):
    results = OrderResponseSerializer(many=True)


class PreviewPriceEvidenceSerializer(PriceEvidenceSerializer):
    bid = serializers.DecimalField(max_digits=36, decimal_places=18)
    ask = serializers.DecimalField(max_digits=36, decimal_places=18)
    mid = serializers.DecimalField(max_digits=36, decimal_places=18)
    provider_health = serializers.CharField()


class OrderPreviewResponseSerializer(serializers.Serializer):
    decision = serializers.CharField()
    reason_codes = serializers.ListField(child=serializers.CharField())
    policy_version = serializers.CharField()
    inputs_hash = serializers.CharField()
    tenant_ref = serializers.CharField()
    account_ref = serializers.CharField()
    instrument = serializers.CharField()
    instrument_symbol = serializers.CharField()
    instrument_version = serializers.IntegerField()
    side = serializers.ChoiceField(choices=("BUY", "SELL"))
    order_type = serializers.ChoiceField(choices=("MARKET", "LIMIT"))
    quantity = serializers.DecimalField(max_digits=36, decimal_places=18)
    price = serializers.DecimalField(max_digits=36, decimal_places=18)
    notional = serializers.DecimalField(max_digits=36, decimal_places=18)
    price_evidence = PreviewPriceEvidenceSerializer()
    fees = FeeEvidenceSerializer()
    estimated_fee = serializers.DecimalField(max_digits=36, decimal_places=18)
    available_simulated_balance = serializers.DecimalField(max_digits=36, decimal_places=18)
    simulation = serializers.BooleanField()


class PositionResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    tenant_ref = serializers.CharField()
    account_ref = serializers.CharField()
    instrument = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=36, decimal_places=18)
    average_price = serializers.DecimalField(max_digits=36, decimal_places=18)
    realized_pnl = serializers.DecimalField(max_digits=36, decimal_places=18)
    simulation = serializers.BooleanField()


class PositionCollectionSerializer(serializers.Serializer):
    results = PositionResponseSerializer(many=True)


class TradeResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    trade_id = serializers.UUIDField()
    order_id = serializers.UUIDField()
    execution_id = serializers.CharField()
    instrument_id = serializers.CharField()
    instrument = serializers.CharField()
    side = serializers.ChoiceField(choices=("BUY", "SELL"))
    quantity = serializers.DecimalField(max_digits=36, decimal_places=18)
    price = serializers.DecimalField(max_digits=36, decimal_places=18)
    gross_notional = serializers.DecimalField(max_digits=36, decimal_places=18)
    fee = serializers.DecimalField(max_digits=36, decimal_places=18)
    currency = serializers.CharField()
    trade_time = serializers.DateTimeField()
    executed_at = serializers.DateTimeField()
    settlement_date = serializers.DateField()
    state = serializers.CharField()
    execution_mode = serializers.CharField()
    simulation = serializers.BooleanField()


class TradeCollectionSerializer(serializers.Serializer):
    results = TradeResponseSerializer(many=True)
