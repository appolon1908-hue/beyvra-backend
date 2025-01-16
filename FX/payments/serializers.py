from datetime import datetime, timedelta

from rest_framework import serializers

from .models import PaymentMethod, Payment


class PaymentRequestSerializer(serializers.Serializer):
    amount = serializers.FloatField()
    wallet_id = serializers.UUIDField()


class BinancePaymentResponseSerializer(serializers.Serializer):
    payment_url = serializers.CharField(required=False, allow_blank=True, default="https://tradx.io/")
    qrcode_url = serializers.CharField(required=False, allow_blank=True, default="https://tradx.io/")
    order_id = serializers.IntegerField(required=False, default=1)
    merchant_trade_no = serializers.CharField(required=False, allow_blank=True, default="ABC")
    status = serializers.CharField(required=False, allow_blank=True, default="Active")
    expiration_time = serializers.DateTimeField(required=False, default=datetime.now() + timedelta(hours=3))
    currency = serializers.CharField(required=False, allow_blank=True, default=None)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True, default=None)
    merchant_name = serializers.CharField(required=False, allow_blank=True, default="Seaflux")
    product_name = serializers.CharField(required=False, allow_blank=True, default=None)
    return_url = serializers.CharField(required=False, allow_blank=True, default="https://tradx.io/")
    cancel_url = serializers.CharField(required=False, allow_blank=True, default="https://tradx.io/")


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = "__all__"


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['payment_id', 'user', 'provider', 'wallet', 'amount', 'type', 'status', 'payment_date', 'reference', 'qr_code_url', 'description']

