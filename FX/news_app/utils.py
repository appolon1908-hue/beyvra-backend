import requests
from django.conf import settings
from django.core.cache import cache
from provider_governance.service import ProviderNotAvailable, resolve_provider


def _governed_news_request(request, query, country):
    resolved = resolve_provider(
        provider_id="newsdata", provider_type="FINANCIAL_NEWS", product="HEADLINES",
        symbol=query.upper(), region=country.upper(), request_id=request.headers.get("X-Request-ID", ""),
        correlation_id=request.headers.get("X-Correlation-ID", ""), caller_service="news-api",
    )
    if not resolved.credential_path:
        raise ProviderNotAvailable("PROVIDER_NOT_AVAILABLE")
    with open(resolved.credential_path, encoding="utf-8") as credential_file:
        credential = credential_file.read().strip()
    if not credential:
        raise ProviderNotAvailable("PROVIDER_NOT_AVAILABLE")
    return credential


def get_newsdata_news(request):
    """Get the latest news from Newsdata API."""

    # Extract query parameters
    req = request.query_params
    query = req.get("query", "cryptocurrency")
    size = req.get("size", 10)
    country = req.get("country", "us")

    credential = _governed_news_request(request, query, country)
    url = f"https://newsdata.io/api/1/latest?q={query}&language=en&country={country}&size={size}"
    cache_key = f"newsdata:{query}:{country}:{size}"

    # Check cache first
    cached_response = cache.get(cache_key)
    if cached_response:
        return cached_response

    # Make the API request
    response = requests.get(url, headers={"X-ACCESS-KEY": credential}, timeout=10)
    response_data = response.json()

    # Remove the 'nextPage' key if it exists
    if "nextPage" in response_data:
        del response_data["nextPage"]

    unwanted_keys = [
        "keywords",
        "ai_tag",
        "sentiment",
        "duplicate",
        "ai_org",
        "source_priority",
        "sentiment_stats",
        "ai_region",
    ]

    for article in response_data["results"]:
        for key in unwanted_keys:
            if key in article:
                del article[key]

    # Cache the modified response
    cache.set(cache_key, response_data, settings.REDIS_CACHE_CUSTOM_TIMEOUT)

    return response_data




def get_newsdata_news_by_id(request, article_id):
    """Get a specific news item by its article_id from the Newsdata API."""

    # Extract query parameters
    req = request.query_params
    query = req.get("query", "cryptocurrency")
    size = req.get("size", 10)
    country = req.get("country", "us")

    credential = _governed_news_request(request, query, country)
    url = f"https://newsdata.io/api/1/latest?q={query}&language=en&country={country}&size={size}"
    cache_key = f"newsdata:{query}:{country}:{size}"

    # Check cache first
    cached_response = cache.get(cache_key)
    if cached_response:
        response_data = cached_response
    else:
        # Make the API request
        response = requests.get(url, headers={"X-ACCESS-KEY": credential}, timeout=10)
        response_data = response.json()

        # Cache the response data
        cache.set(cache_key, response_data, settings.REDIS_CACHE_CUSTOM_TIMEOUT)

    # Filter for the specific article by article_id
    for article in response_data["results"]:
        if article["article_id"] == article_id:
            return article

    # If no article found with the given article_id
    return {"error": "Article not found"}
