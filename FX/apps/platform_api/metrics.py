from prometheus_client import Counter, Histogram


webhooks_total = Counter(
    "beyvra_webhooks_total",
    "Inbound webhook outcomes.",
    ("provider", "webhook_type", "result"),
)
webhook_latency_seconds = Histogram(
    "beyvra_webhook_processing_seconds",
    "Webhook authentication and persistence latency.",
    ("provider", "webhook_type"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2),
)
api_idempotency_total = Counter(
    "beyvra_api_idempotency_total",
    "Canonical API idempotency outcomes.",
    ("scope", "result"),
)
