from django.core.cache import cache
from django.db.models import Sum
from .models import Transaction, Revenue, UserActivity, Trade, Report
from typing import Union
from datetime import date

def get_or_set_metrics_cache(start_date: Union[date, None], end_date: Union[date, None], **kwargs) -> dict:
    result = {}

    if 'categories' in kwargs:
        categories = kwargs['categories']

        #cache.get(
        
