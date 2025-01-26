from rest_framework import serializers
from wsnotifications.models import PriceAlert




class PriceAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceAlert