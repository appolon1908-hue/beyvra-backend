import datetime

import requests
from django.conf import settings
from django.core.cache import cache
from provider_governance.service import ProviderNotAvailable, resolve_provider


def get_news(request):
    """Get the latest news from Alpaca API."""
    req = request.query_params
    resolved = resolve_provider(
        provider_id="alpaca_news", provider_type="FINANCIAL_NEWS", product="HEADLINES",
        symbol="*", region="GLOBAL", request_id=request.headers.get("X-Request-ID", ""),
        correlation_id=request.headers.get("X-Correlation-ID", ""), caller_service="alpaca-news-api",
    )
    if not resolved.credential_path:
        raise ProviderNotAvailable("PROVIDER_NOT_AVAILABLE")
    with open(resolved.credential_path, encoding="utf-8") as credential_file:
        api_key, api_secret = credential_file.read().strip().split(":", 1)
    url = f"https://data.alpaca.markets/v1beta1/news?&limit={req.get('limit')}&sort={req.get('sort')}&include_content={req.get('include_content')}&exclude_contentless={req.get('exclude_contentless')}"  # noqa

    headers = {
        "accept": "application/json",
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
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
