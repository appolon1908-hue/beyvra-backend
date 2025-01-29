from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from api_trade.utils.alpaca_util import validate_date_range
from datetime import datetime, date
from .utils import validate_filters_for_categories

class DashboardMetricsSerializer(serializers.Serializer):
    
    start_date = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])
    end_date = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])
    categories_filters = serializers.CharField(required=False)

    def validate_categories_filters(self, value):
        validate_filters_for_categories(value)
        
        return value

    def validate(self, data):
        start_date = data.get('start_date', None)
        start_date = serializers.DateField().to_representation(start_date) if start_date else start_date
        end_date = data.get('end_date', None)
        end_date = serializers.DateField().to_representation(end_date) if end_date else end_date

        if not start_date and not end_date:
            raise ValidationError('Requiring at least one date range parameter("start_date", "end_date").')
        
        if start_date:
            validate_date_range(
                start_date,
                end_date,
                datetime.now().strftime('%Y-%m-%d'),
            )
            
        return data