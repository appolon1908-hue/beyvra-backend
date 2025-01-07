import datetime

import requests
from django.conf import settings
from django.core.cache import cache


def get_news(request):
    """Get the latest news from Alpaca API."""
    req = request.query_params
    url = f"https://data.alpaca.markets/v1beta1/news?&limit={req.get('limit')}&sort={req.get('sort')}&include_content={req.get('include_content')}&exclude_contentless={req.get('exclude_contentless')}"  # noqa

    headers = {
        "accept": "application/json",
        "APCA-API-KEY-ID": settings.API_KEY_ALPACA,
        "APCA-API-SECRET-KEY": settings.SECRET_KEY_ALPACA,
    }
    cached_response = cache.get(url)
    if cached_response:
        return cached_response
    response = requests.get(url, headers=headers)
    response = response.json()

    for news in response["news"]:
        created_at = datetime.datetime.strptime(news["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        updated_at = datetime.datetime.strptime(news["updated_at"], "%Y-%m-%dT%H:%M:%SZ")

        news["created_at"] = int(created_at.timestamp())
        news["updated_at"] = int(updated_at.timestamp())

    cache.set(url, response, settings.REDIS_CACHE_CUSTOM_TIMEOUT)

    return response
