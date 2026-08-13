from prometheus_client import Counter, Gauge, Histogram


REQUESTS = Counter(
    "beyvra_financial_client_requests_total",
    "Logical Financial Service client requests.",
    ("method", "outcome"),
)
FAILURES = Counter(
    "beyvra_financial_client_failures_total",
    "Financial Service client failures excluding expected feature gates.",
    ("category",),
)
DURATION = Histogram(
    "beyvra_financial_client_duration_seconds",
    "Logical Financial Service client request duration.",
    ("method",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
IDEMPOTENCY_CONFLICTS = Counter(
    "beyvra_financial_idempotency_conflicts_total",
    "Financial Service idempotency conflicts.",
)
UNKNOWN_OUTCOMES = Counter(
    "beyvra_financial_unknown_outcomes_total",
    "Financial mutations with ambiguous outcomes.",
)
CIRCUIT_STATE = Gauge(
    "beyvra_financial_circuit_breaker_state",
    "Financial client circuit state (0 closed, 1 half-open, 2 open).",
)


SAFE_FAILURE_CATEGORIES = {
    "MTLS_AUTHENTICATION_FAILED", "TRANSIENT_UNAVAILABLE", "UNKNOWN_OUTCOME",
    "IDEMPOTENCY_CONFLICT", "VALIDATION_ERROR", "RESTRICTION", "NOT_FOUND",
    "FINANCIAL_SERVICE_ERROR", "SERVICE_TEMPORARILY_UNAVAILABLE",
}


def failure_category(code: str) -> str:
    return code if code in SAFE_FAILURE_CATEGORIES else "FINANCIAL_SERVICE_ERROR"
