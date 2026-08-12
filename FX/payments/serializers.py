from datetime import datetime, timedelta
from decimal import Decimal

from rest_framework import serializers

from .models import PaymentMethod, Payment


class PaymentRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    wallet_id = serializers.IntegerField()


class PaymentProcessingSerializer(PaymentRequestSerializer):
    payment_method_id = serializers.IntegerField(min_value=1)


class WalletTransferSerializer(serializers.Serializer):
    source_wallet_id = serializers.IntegerField(min_value=1)
    target_wallet_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(
        max_digits=20,
        decimal_places=8,
        min_value=Decimal("0.00000001"),
    )

    def validate(self, attrs):
        if attrs["source_wallet_id"] == attrs["target_wallet_id"]:
            raise serializers.ValidationError("Source and target wallets must differ.")
        return attrs


class BinancePaymentResponseSerializer(serializers.Serializer):
    payment_url = serializers.CharField(required=False, allow_blank=True, default="https://beyvra.com/")
    qrcode_url = serializers.CharField(required=False, allow_blank=True, default="https://beyvra.com/")
    order_id = serializers.IntegerField(required=False, default=1)
    merchant_trade_no = serializers.CharField(required=False, allow_blank=True, default="ABC")
    status = serializers.CharField(required=False, allow_blank=True, default="Active")
    expiration_time = serializers.DateTimeField(required=False, default=datetime.now() + timedelta(hours=3))
    currency = serializers.CharField(required=False, allow_blank=True, default=None)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True, default=None)
    merchant_name = serializers.CharField(required=False, allow_blank=True, default="Seaflux")
    product_name = serializers.CharField(required=False, allow_blank=True, default=None)
    return_url = serializers.CharField(required=False, allow_blank=True, default="https://beyvra.com/")
    cancel_url = serializers.CharField(required=False, allow_blank=True, default="https://beyvra.com/")


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = "__all__"


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['payment_id', 'user', 'provider', 'wallet', 'amount', 'type', 'status', 'payment_date', 'reference', 'qr_code_url', 'description']
        read_only_fields = ['payment_id', 'user', 'status', 'payment_date']

    def validate_wallet(self, wallet):
        request = self.context.get('request')
        if request is None or wallet.user_id != request.user.id:
            raise serializers.ValidationError('Wallet does not belong to the authenticated user.')
        return wallet
