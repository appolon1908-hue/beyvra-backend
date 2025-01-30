from django.core.cache import cache
from django.db.models import Sum
from .models import Transaction, Revenue, UserActivity, Trade
from typing import Union
from datetime import date, datetime
import json
import hashlib
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

# Settings related with categories filters
cfilters_datetime_format = '%Y-%m-%d %H:%M:%S'
cfilters_types_rules = {
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
                                'type_check_funct': lambda val: type(val) is str and is_correct_datetime_string(val, cfilters_datetime_format),
                                'type_name': 'datetime(' + cfilters_datetime_format + ')',
                    },
                    'bool': {
                                'operators': ['='], 
                                'type': bool,
                    },
                }
cfilters_conf = {
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


# This method can be executed ONLY when "categories_filters" is valid
def get_or_set_metrics_cache(start_date: Union[date, None], end_date: Union[date, None], categories_filters: Union[str, None]) -> dict:
    # Generate hashed key for caching metrics
    params = {
                'start_date': serializers.DateField().to_representation(start_date) if start_date else 'none',
                'end_date': serializers.DateField().to_representation(end_date) if end_date else 'none',
                'categories_filters': categories_filters if categories_filters else 'none',
            }
    metrics_key = generate_hashed_key('dashboard_metrics', params)

    # Check cache first
    cached_response = cache.get(metrics_key)
    if cached_response:
        return json.loads(cached_response)

    prepared_filters = prepare_filters_for_dashboard_metrics(start_date, end_date, categories_filters)

    transactions_metric = Transaction.objects.filter(**prepared_filters['transactions']).aggregate(Sum('amount')).get('amount__sum', 0)
    transactions_metric = float(transactions_metric) if transactions_metric else 0
    revenue_metric = Revenue.objects.filter(**prepared_filters['revenues']).aggregate(Sum('amount')).get('amount__sum', 0)
    revenue_metric = float(revenue_metric) if revenue_metric else 0
    user_activity = UserActivity.objects.filter(**prepared_filters['users_activities']).count()

    data = {
        "transactions": transactions_metric,
        "revenue": revenue_metric,
        "transaction_volumes": Transaction.objects.filter(**prepared_filters['transactions']).count(),
        "user_activity": user_activity,
        "total_trades": Trade.objects.filter(**prepared_filters['trades']).count(),
        #"system_health": SystemHealth.get_status(),
    }
    # Cache ready metrics as json
    cache.set(metrics_key, json.dumps(data))
    
    return data

def is_correct_datetime_string(datetime_string: str, format: str) -> bool:
    try:
        datetime.strptime(datetime_string, format)
        return True
    except ValueError:
        return False

def generate_hashed_key(prefix: str, params: dict) -> str:
    result = prefix
    for key, value in params.items():
        result += f'&{key}={value}'
    
    return hashlib.md5(result.encode()).hexdigest()

def validate_filters_for_categories(value: str):
    prepared_data = json.loads(value)

    if type(prepared_data) is dict:
        if 'categories' in prepared_data and type(prepared_data['categories']) is list:
            if len(prepared_data['categories']) == 0:
                raise ValidationError(f'"categories" Array is empty. It must contain at least 1 category.')
            
            for category_dict in prepared_data['categories']:
                if type(category_dict) is dict and 'name' in category_dict and type(category_dict['name']) is str and 'filters' in category_dict and type(category_dict['filters']) is list:
                    cat_name = category_dict['name']

                    if cat_name in cfilters_conf:
                        filters = category_dict['filters']
                        if len(filters) == 0:
                            raise ValidationError(f'"filters" Array for category "{cat_name}" is empty. It must contain at least 1 filter.')

                        allowed_category_fields = cfilters_conf[cat_name]
                        for filter_dict in filters:
                            if type(filter_dict) is dict and 'field' in filter_dict and type(filter_dict['field']) is str and 'operator' in filter_dict and type(filter_dict['operator']) is str and 'value' in filter_dict:
                                filter_field = filter_dict['field']
                                filter_operator = filter_dict['operator']
                                filter_value = filter_dict['value']
                                if filter_field in allowed_category_fields:
                                    field_type = allowed_category_fields[filter_field]
                                    type_rules = cfilters_types_rules[field_type]
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
    
def prepare_filters_for_dashboard_metrics(start_date: Union[date, None], end_date: Union[date, None], categories_filters_json: Union[str, None]) -> dict:
    categories_filters = json.loads(categories_filters_json) if categories_filters_json else categories_filters_json
    prepared_filters = {
                            'transactions': {},
                            'revenues': {},
                            'users_activities': {'is_active': True},
                            'trades': {},
                        }
    
    start_datetime = datetime.combine(start_date, datetime.min.time()) if start_date else None
    end_datetime = datetime.combine(end_date, datetime.max.time()) if end_date else None
    
    if start_datetime:
        prepared_filters['transactions']['date__gte'] = start_datetime
        prepared_filters['revenues']['date__gte'] = start_datetime
        prepared_filters['trades']['trade_date__gte'] = start_datetime

    if end_datetime:
        prepared_filters['transactions']['date__lte'] = end_datetime
        prepared_filters['revenues']['date__lte'] = end_datetime
        prepared_filters['trades']['trade_date__lte'] = end_datetime
    
    if categories_filters:
        operators_helpers = {
                                '=': '',
                                '>': '__gt',
                                '<': '__lt',
                                '<=': '__lte',
                                '>=': '__gte',
                                'like': '__icontains',
                            }
        
        for category in categories_filters['categories']:
            cat_name = category['name']
            for filter_dict in category['filters']:
                filter_operator = filter_dict['operator']
                filter_key = filter_dict['field'] + operators_helpers[filter_operator]
                prepared_filters[cat_name][filter_key] = filter_dict['value']

    return prepared_filters
    
    