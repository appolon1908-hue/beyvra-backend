from django.core.cache import cache
from django.db.models import Sum
from .models import Transaction, Revenue, UserActivity, Trade
from typing import Union
from datetime import date, datetime
import json
import hashlib

# This method can be executed ONLY when "categories_filters" is valid
def get_or_set_metrics_cache(url: str, start_date: Union[date, None], end_date: Union[date, None], categories_filters: Union[str, None]) -> dict:
    # Create completed URL which includes date range parameters and categories_filters
    start_date_param = start_date.strftime('%Y-%m-%d') if start_date else 'none'
    end_date_param = end_date.strftime('%Y-%m-%d') if end_date else 'none'
    categories_filters_param = categories_filters if categories_filters else 'none'

    metrics_key = hashlib.md5(f'{url}?start_date={start_date_param}&end_date={end_date_param}&categories_filters={categories_filters_param}'.encode()).hexdigest()

    # Check cache first
    cached_response = cache.get(metrics_key)
    if cached_response:
        return json.loads(cached_response)

    categories_filters = json.loads(categories_filters) if categories_filters else categories_filters
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
    
    user_activity = UserActivity.objects.filter(**prepared_filters['users_activities']).count()

    data = {
        "transactions": float(Transaction.objects.filter(**prepared_filters['transactions']).aggregate(Sum('amount'))['amount__sum']),
        "revenue": float(Revenue.objects.filter(**prepared_filters['revenues']).aggregate(Sum('amount'))['amount__sum']),
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
    
