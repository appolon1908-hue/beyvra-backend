"""Compatibility functions backed by the canonical NewsData client."""
import requests  # compatibility patch target; transport remains in newsdata.NewsDataClient
from .service import fetch_newsdata

def get_newsdata_news(request): return fetch_newsdata(request, "latest")
def get_newsdata_news_by_id(request, article_id): return fetch_newsdata(request, "latest", article_id=article_id)
