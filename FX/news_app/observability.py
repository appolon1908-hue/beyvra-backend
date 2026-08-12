from prometheus_client import Counter, Gauge, Histogram

PROVIDER_REQUESTS = Counter("beyvra_news_provider_requests_total", "News provider requests", ("provider", "endpoint", "result", "environment"))
PROVIDER_FAILURES = Counter("beyvra_news_provider_failures_total", "News provider failures", ("provider", "endpoint", "result", "environment"))
PROVIDER_RATE_LIMITED = Counter("beyvra_news_provider_rate_limited_total", "News provider rate limits", ("provider", "endpoint", "result", "environment"))
PROVIDER_DURATION = Histogram("beyvra_news_provider_duration_seconds", "News provider latency", ("provider", "endpoint", "result", "environment"))
ARTICLES_INGESTED = Counter("beyvra_news_articles_ingested_total", "Canonical news articles ingested", ("provider", "endpoint"))
ARTICLES_DEDUPLICATED = Counter("beyvra_news_articles_deduplicated_total", "Duplicate news articles suppressed", ("provider",))
INGESTION_FAILURES = Counter("beyvra_news_ingestion_failures_total", "News ingestion failures", ("provider", "category"))
LAST_SUCCESS = Gauge("beyvra_news_last_success_timestamp_seconds", "Last successful news ingestion", ("provider", "endpoint"))
NEWS_AGE = Gauge("beyvra_news_age_seconds", "Age of newest canonical article", ("provider", "endpoint"))

