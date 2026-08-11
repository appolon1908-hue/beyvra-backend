import requests
import hashlib
from django.conf import settings
from django.core.cache import cache


def get_newsdata_news(request):
    """Get the latest news from Newsdata API."""

    # Extract query parameters
    req = request.query_params
    query = req.get("query", "cryptocurrency")
    size = req.get("size", 10)
    country = req.get("country", "us")

    # Construct the API URL
    url = f"https://newsdata.io/api/1/latest?apikey={settings.NEWS_DATA_API_KEY}&q={query}&language=en&country={country}&size={size}"

    # Check cache first
    cache_key = "newsdata:" + hashlib.sha256(
        f"{query}|{country}|{size}".encode("utf-8")
    ).hexdigest()
    cached_response = cache.get(cache_key)
    if cached_response:
        return cached_response

    # Make the API request
    response = requests.get(url)
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

    # Construct the API URL
    url = f"https://newsdata.io/api/1/latest?apikey={settings.NEWS_DATA_API_KEY}&q={query}&language=en&country={country}&size={size}"

    # Check cache first
    cache_key = "newsdata:" + hashlib.sha256(
        f"{query}|{country}|{size}".encode("utf-8")
    ).hexdigest()
    cached_response = cache.get(cache_key)
    if cached_response:
        response_data = cached_response
    else:
        # Make the API request
        response = requests.get(url)
        response_data = response.json()

        # Cache the response data
        cache.set(cache_key, response_data, settings.REDIS_CACHE_CUSTOM_TIMEOUT)

    # Filter for the specific article by article_id
    for article in response_data["results"]:
        if article["article_id"] == article_id:
            return article

    # If no article found with the given article_id
    return {"error": "Article not found"}
