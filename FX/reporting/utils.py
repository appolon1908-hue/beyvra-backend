from django.core.cache import cache
from django.db.models import Sum
from .models import Transaction, Revenue, UserActivity, Trade, Report
from typing import Union
from datetime import date, datetime
import json
from django.conf import settings

# This method can be executed ONLY when "categories_filters" is valid
def get_or_set_metrics_cache(url: str, start_date: Union[date, None], end_date: Union[date, None], categories_filters: Union[str, None]) -> dict:
    # Create completed URL which includes date range parameters and categories_filters
    completed_url = url + '?start_date=' + start_date.strftime('%Y-%m-%d') + '&end_date=' + end_date.strftime('%Y-%m-%d') + '&categories_filters=' + categories_filters 
    # Check cache first
    cached_response = cache.get(completed_url)
    if cached_response:
        return cached_response

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
    
    data = {
        "transactions_count": Transaction.objects.filter(prepared_filters['transactions']).count(),
        "revenue": Revenue.objects.filter(prepared_filters['revenues']).aggregate(Sum('amount')),
        "transaction_volumes": Transaction.objects.filter(prepared_filters['transactions']).aggregate(Sum('amount')),
        "user_activity": UserActivity.objects.filter(prepared_filters['users_activities']).count(),
        "total_trades": Trade.objects.filter(prepared_filters['trades']).count(),
        #"system_health": SystemHealth.get_status(),
    }

    # Cache ready metrics as json
    json_data = json.dumps(data)
    cache.set(completed_url, json_data)
    
    return json_data

def is_correct_datetime_string(datetime_string: str, format: str) -> bool:
    try:
        datetime.strptime(datetime_string, format)
        return True
    except ValueError:
        return False
    
