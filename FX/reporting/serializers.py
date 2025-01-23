from rest_framework import status
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from api_trade.utils.alpaca_util import validate_date_range
from .utils import is_correct_datetime_string
from datetime import datetime, date
import json

class DashboardMetricsSerializer(serializers.Serializer):
    datetime_format = '%Y-%m-%d %H:%M:%S'

    @property
    def types_rules(self) -> dict: 
        return {
            'integer': {
                        'operators': ['=', '>', '<', '<=', '>=',], 
                        'type': int,
            },
            'decimal': {
                        'operators': ['=', '>', '<', '<=', '>=',], 
                        'type_check_funct': lambda val: type(val) is float or type(val) is int,
                        'type_name': 'decimal',
            },
            'char': {
                        'operators': ['=', 'like',], 
                        'type': str,
            },
            'text': {
                        'operators': ['=', 'like',], 
                        'type': str,
            },
            'datetime': {
                        'operators': ['=', '>', '<', '<=', '>=',], 
                        'type_check_funct': lambda val: type(val) is str and is_correct_datetime_string(val, self.datetime_format),
                        'type_name': 'datetime(' + self.datetime_format + ')',
            },
            'bool': {
                        'operators': ['='], 
                        'type': bool,
            },
        }
    
    @property
    def filters_conf(self) -> dict:
        return {
                'transactions': {
                                    'user': 'integer',
                                    'amount': 'decimal',
                                    'date': 'datetime',
                                    'transaction_type': 'char',
                                    'category': 'char',
                                },
                'revenues': {
                                'date': 'datetime',
                                'amount': 'decimal',
                            },
                'users_activities': {
                                        'user': 'integer',
                                        'last_active': 'datetime',
                                        'is_active': 'bool',
                                    },
                'trades': {
                            'user': 'integer',
                            'asset': 'char',
                            'trade_volume': 'decimal',
                            'trade_date': 'datetime',
                        },
                }
    
    start_date = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])
    end_date = serializers.DateField(required=False, input_formats=['%Y-%m-%d'])
    categories_filters = serializers.CharField(required=False) #serializers.JSONField(required=False)

    def validate_categories_filters(self, value):
        prepared_data = json.loads(value)

        if type(prepared_data) is dict:
            if 'categories' in prepared_data and type(prepared_data['categories']) is list:
                if len(prepared_data['categories']) == 0:
                    raise ValidationError(f'"categories" Array is empty. It must contain at least 1 category.')

                for category_dict in prepared_data['categories']:
                    if type(category_dict) is dict and 'name' in category_dict and type(category_dict['name']) is str and 'filters' in category_dict and type(category_dict['filters']) is list:
                        cat_name = category_dict['name']

                        if cat_name in self.filters_conf:
                            filters = category_dict['filters']
                            if len(filters) == 0:
                                raise ValidationError(f'"filters" Array for category "{cat_name}" is empty. It must contain at least 1 filter.')

                            allowed_category_fields = self.filters_conf[cat_name]
                            for filter_dict in filters:
                                if type(filter_dict) is dict and 'field' in filter_dict and type(filter_dict['field']) is str and 'operator' in filter_dict and type(filter_dict['operator']) is str and 'value' in filter_dict:
                                    filter_field = filter_dict['field']
                                    filter_operator = filter_dict['operator']
                                    filter_value = filter_dict['value']
                                    if filter_field in allowed_category_fields:
                                        field_type = allowed_category_fields[filter_field]
                                        type_rules = self.types_rules[field_type]
                                        # Check if filter operator is allowed
                                        if filter_operator not in type_rules['operators']:
                                            raise ValidationError(f'Filter operator "{filter_operator}" is not allowed for "{field_type}" field')
                                        
                                        # Check if filter value has correct type
                                        if 'type_check_funct' in type_rules:
                                            if not type_rules['type_check_funct'](filter_value):
                                                raise ValidationError('Type of value {} doesn\'t match with "{}"'.format(filter_value, type_rules['type_name']))   
                                        elif type(filter_value) is not type_rules['type']:
                                            raise ValidationError('Type of value {} doesn\'t match with "{}"'.format(filter_value, type_rules['type'].__name__))
                                    else:
                                        raise ValidationError(f'Field "{filter_field}" is not allowed for filtering category "{cat_name}"')
                                else:
                                    raise ValidationError('Each filter must be object with properties "field"(type "string"), "operator"(type "string"), "value"')
                        else:
                            raise ValidationError(f'There is no category with name "{cat_name}"')
                    else:
                        raise ValidationError('Each category must be object with properties "name"(type "String"), "filters"(type "Array")')
            else:
                raise ValidationError('JSON object must have property "categories"(type "Array").')
        else:
            raise ValidationError('Value must be JSON object')
        
        return value

    def validate(self, data):
        start_date = data.get('start_date', None)
        start_date = start_date.strftime('%Y-%m-%d') if start_date else start_date
        end_date = data.get('end_date', None)
        end_date = end_date.strftime('%Y-%m-%d') if end_date else end_date

        if not start_date and not end_date:
            raise ValidationError('Requiring at least one date range parameter("start_date", "end_date").')
        
        if start_date:
            validate_date_range(
                start_date,
                end_date,
                datetime.now().strftime('%Y-%m-%d'),
            )
            
        return data