from rest_framework import serializers
from .models import AccountPlan, SubscriptionPrice


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountPlan
        fields = ("code", "name", "description_safe", "effective_from", "effective_to")


class FeePreviewSerializer(serializers.Serializer):
    fee_type = serializers.ChoiceField(choices=("TRADING_COMMISSION","WITHDRAWAL","TRANSFER"))
    notional = serializers.DecimalField(max_digits=30, decimal_places=12)
    quantity = serializers.DecimalField(max_digits=30, decimal_places=12)
    asset_class = serializers.CharField(required=False, default="")
