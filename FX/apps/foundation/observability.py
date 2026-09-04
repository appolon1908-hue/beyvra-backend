"""Bounded-cardinality Beyvra metrics. Never add identity or raw URL labels."""

import os
import time
from contextlib import contextmanager

from prometheus_client import Counter, Gauge, Histogram

ENVIRONMENT = os.getenv("DEPLOYMENT_ENV", "unknown")
HTTP_LABELS = ("method", "route_template", "status_class", "environment")

HTTP_REQUESTS = Counter(
    "beyvra_http_requests_total",
    "Canonical HTTP requests",
    HTTP_LABELS,
)
HTTP_DURATION = Histogram(
    "beyvra_http_request_duration_seconds",
    "Canonical HTTP latency",
    HTTP_LABELS,
)
ORDERS = Counter(
    "beyvra_trading_orders_created_total",
    "Created orders",
    ("environment", "simulation"),
)
ORDERS_REJECTED = Counter(
    "beyvra_trading_orders_rejected_total",
    "Rejected orders",
    ("environment", "simulation"),
)
ORDERS_CANCELLED = Counter(
    "beyvra_trading_orders_cancelled_total",
    "Cancelled orders",
    ("environment", "simulation"),
)
ORDERS_FILLED = Counter(
    "beyvra_trading_orders_filled_total",
    "Filled orders",
    ("environment", "simulation"),
)
ORDERS_PARTIAL = Counter(
    "beyvra_trading_orders_partially_filled_total",
    "Partially filled orders",
    ("environment", "simulation"),
)
ORDER_DURATION = Histogram(
    "beyvra_trading_order_processing_duration_seconds",
    "Order processing latency",
    ("environment", "simulation"),
)
ORDERS_IN_STATE = Gauge(
    "beyvra_trading_orders_in_state",
    "Orders by state",
    ("state", "environment", "simulation"),
)
RISK_DECISIONS = Counter(
    "beyvra_risk_decisions_total",
    "Risk decisions",
    ("decision", "reason_category", "policy_version", "simulation"),
)
RISK_DURATION = Histogram(
    "beyvra_risk_decision_duration_seconds",
    "Risk evaluation latency",
    ("simulation",),
)
SIM_RESERVATIONS = {
    state: Counter(
        f"beyvra_sim_reservations_{state}_total",
        f"Simulated reservations {state}",
    )
    for state in ("created", "released", "consumed")
}
SIM_RESERVATIONS_ACTIVE = Gauge(
    "beyvra_sim_reservations_active",
    "Active simulated reservations",
)
SIM_RESERVATION_AGE = Gauge(
    "beyvra_sim_reservation_age_seconds",
    "Oldest active simulated reservation age",
)
SIM_RESERVATION_OLDEST_AGE = Gauge(
    "beyvra_sim_reservation_oldest_age_seconds",
    "Oldest active simulated reservation age",
)
SIM_SETTLEMENTS = Counter(
    "beyvra_sim_settlements_total",
    "Simulated settlements",
    ("result",),
)
SIM_SETTLEMENT_FAILURES = Counter(
    "beyvra_sim_settlement_failures_total",
    "Simulated settlement failures",
    ("failure_category",),
)
SIM_SETTLEMENT_DURATION = Histogram(
    "beyvra_sim_settlement_duration_seconds",
    "Simulated settlement latency",
)
INVARIANT_COUNTERS = {
    name: Counter(name, "Detected simulation invariant violation")
    for name in (
        "beyvra_sim_duplicate_settlement_detected_total",
        "beyvra_sim_negative_balance_detected_total",
        "beyvra_sim_reservation_leak_detected_total",
        "beyvra_sim_position_accounting_error_total",
        "beyvra_duplicate_business_effect_detected_total",
        "beyvra_tenant_isolation_violation_total",
    )
}
OUTBOX_PENDING = Gauge(
    "beyvra_outbox_pending_events",
    "Pending and claimed outbox events",
)
OUTBOX_AGE = Gauge(
    "beyvra_outbox_oldest_pending_age_seconds",
    "Oldest pending outbox age",
)
OUTBOX_PUBLISHED = Counter(
    "beyvra_outbox_published_total",
    "Published outbox events",
)
OUTBOX_FAILURES = Counter(
    "beyvra_outbox_publish_failures_total",
    "Outbox publish failures",
    ("failure_category",),
)
OUTBOX_RETRIES = Counter(
    "beyvra_outbox_retries_total",
    "Outbox retries",
)
OUTBOX_LAST_SUCCESS = Gauge(
    "beyvra_outbox_worker_last_success_timestamp_seconds",
    "Outbox last success",
)
INBOX_PROCESSED = Counter(
    "beyvra_inbox_events_processed_total",
    "Inbox events",
    ("consumer_type",),
)
INBOX_DUPLICATES = Counter(
    "beyvra_inbox_duplicate_events_total",
    "Duplicate inbox events",
    ("consumer_type",),
)
INBOX_FAILURES = Counter(
    "beyvra_inbox_processing_failures_total",
    "Inbox failures",
    ("consumer_type",),
)
IDEMPOTENCY = Counter(
    "beyvra_idempotency_requests_total",
    "Idempotency outcomes",
    ("result",),
)
JETSTREAM_LAG = Gauge(
    "beyvra_jetstream_consumer_lag",
    "JetStream consumer lag",
    ("consumer_type",),
)
JETSTREAM_REDELIVERIES = Counter(
    "beyvra_jetstream_redeliveries_total",
    "JetStream redeliveries",
    ("consumer_type",),
)
NATS_RECONNECTS = Counter(
    "beyvra_nats_reconnects_total",
    "NATS reconnects",
    ("service",),
)
REALTIME_CONNECTIONS = Gauge(
    "beyvra_realtime_connections",
    "Realtime connections",
)
REALTIME_CONNECT = Counter(
    "beyvra_realtime_connect_total",
    "Realtime connects",
)
REALTIME_DISCONNECT = Counter(
    "beyvra_realtime_disconnect_total",
    "Realtime disconnects",
    ("reason_category",),
)
REALTIME_RECONNECT = Counter(
    "beyvra_realtime_reconnect_total",
    "Realtime reconnects",
)
REALTIME_EVENTS = Counter(
    "beyvra_realtime_events_published_total",
    "Realtime publications",
    ("event_category",),
)
REALTIME_FAILURES = Counter(
    "beyvra_realtime_publish_failures_total",
    "Realtime publish failures",
    ("failure_category",),
)
REALTIME_GAPS = Counter(
    "beyvra_realtime_sequence_gap_total",
    "Realtime sequence gaps",
)
REALTIME_RECOVERY = Counter(
    "beyvra_realtime_snapshot_recovery_total",
    "Realtime snapshot recoveries",
    ("result",),
)
REALTIME_RECOVERY_FAILURES = Counter(
    "beyvra_realtime_snapshot_recovery_failures_total",
    "Realtime snapshot recovery failures",
    ("failure_category",),
)
MARKET_AGE = Gauge(
    "beyvra_market_data_age_seconds",
    "Age of latest accepted market data",
    ("provider",),
)
MARKET_STALE = Counter(
    "beyvra_market_data_stale_total",
    "Market data stale decisions",
    ("provider",),
)
MARKET_REQUESTS = Counter(
    "beyvra_market_provider_requests_total",
    "Governed outbound market requests",
    ("provider", "result"),
)
MARKET_FAILURES = Counter(
    "beyvra_market_provider_failures_total",
    "Market provider failures",
    ("provider", "failure_category"),
)
EXECUTION_ROUTE_DECISIONS = Counter(
    "beyvra_execution_route_decisions_total",
    "Execution route decisions",
    ("mode", "decision"),
)
EXECUTION_PROVIDER_HEALTH = Gauge(
    "beyvra_execution_provider_health",
    "Execution provider health state",
    ("provider", "mode"),
)
EXECUTION_PROVIDER_FAILURES = Counter(
    "beyvra_execution_provider_failures_total",
    "Execution provider failures",
    ("provider", "failure_category"),
)
EXECUTION_ROUTE_DURATION = Histogram(
    "beyvra_execution_route_duration_seconds",
    "Execution route evaluation latency",
    ("mode",),
)
EXECUTION_SLIPPAGE_BPS = Histogram(
    "beyvra_execution_slippage_bps",
    "Measured side-aware simulated or paper execution slippage",
    ("provider", "mode"),
)
EXECUTION_UNKNOWN_OUTCOMES = Counter(
    "beyvra_execution_unknown_outcomes_total",
    "Ambiguous execution outcomes",
    ("provider", "mode"),
)
EXECUTION_ROUTE_REQUESTS = Counter(
    "beyvra_execution_route_requests_total",
    "Execution routing requests",
    ("asset_class", "order_type", "result", "mode"),
)
EXECUTION_ROUTE_CANDIDATES = Counter(
    "beyvra_execution_route_candidates_total",
    "Generated route candidates",
    ("provider", "asset_class", "order_type", "result", "mode"),
)
EXECUTION_ROUTE_SELECTED = Counter(
    "beyvra_execution_route_selected_total",
    "Selected execution routes",
    ("provider", "venue_class", "asset_class", "order_type", "mode"),
)
EXECUTION_ROUTE_REJECTIONS = Counter(
    "beyvra_execution_route_rejections_total",
    "Rejected execution routes",
    ("provider", "asset_class", "order_type", "result", "mode"),
)
EXECUTION_PROVIDER_REQUESTS = Counter(
    "beyvra_execution_provider_requests_total",
    "Paper/simulation provider requests",
    ("provider", "result", "mode"),
)
EXECUTION_PROVIDER_LATENCY = Histogram(
    "beyvra_execution_provider_latency_seconds",
    "Paper/simulation provider latency",
    ("provider", "mode"),
)
EXECUTION_PROVIDER_REJECTIONS = Counter(
    "beyvra_execution_provider_rejections_total",
    "Provider rejections",
    ("provider", "asset_class", "order_type", "mode"),
)
EXECUTION_PARTIAL_FILLS = Counter(
    "beyvra_execution_partial_fills_total",
    "Partial execution fills",
    ("provider", "asset_class", "mode"),
)
EXECUTION_QUALITY_SLIPPAGE = Histogram(
    "beyvra_execution_quality_slippage_bps",
    "Side-aware execution slippage",
    ("provider", "asset_class", "mode"),
)
EXECUTION_PRICE_IMPROVEMENT = Histogram(
    "beyvra_execution_price_improvement_bps",
    "Side-aware price improvement",
    ("provider", "asset_class", "mode"),
)
EXECUTION_RECONCILIATION_VIOLATIONS = Counter(
    "beyvra_execution_reconciliation_violations_total",
    "Execution reconciliation violations",
    ("result",),
)
EXECUTION_CIRCUIT_BREAKER = Gauge(
    "beyvra_execution_circuit_breaker_state",
    "Execution circuit state: closed=0 half-open=1 open=2",
    ("provider", "mode"),
)
MARKET_DURATION = Histogram(
    "beyvra_market_provider_duration_seconds",
    "Market provider latency",
    ("provider",),
)
PROVIDER_UP = Gauge(
    "beyvra_provider_up",
    "Provider connection availability",
    ("provider", "data_type", "asset_class", "environment"),
)
PROVIDER_REQUESTS = Counter(
    "beyvra_provider_requests_total",
    "Provider requests",
    ("provider", "data_type", "asset_class", "environment"),
)
PROVIDER_FAILURES = Counter(
    "beyvra_provider_failures_total",
    "Provider failures",
    ("provider", "data_type", "asset_class", "environment"),
)
PROVIDER_RATE_LIMITED = Counter(
    "beyvra_provider_rate_limited_total",
    "Provider rate-limit responses",
    ("provider", "data_type", "asset_class", "environment"),
)
PROVIDER_LATENCY = Histogram(
    "beyvra_provider_latency_seconds",
    "Provider latency",
    ("provider", "data_type", "asset_class", "environment"),
)
PROVIDER_RECONNECTS = Counter(
    "beyvra_provider_reconnects_total",
    "Provider reconnect attempts",
    ("provider", "data_type", "asset_class", "environment"),
)
PROVIDER_SEQUENCE_GAPS = Counter(
    "beyvra_provider_sequence_gaps_total",
    "Provider sequence gaps",
    ("provider", "data_type", "asset_class", "environment"),
)
MARKET_DATA_AGE = Gauge(
    "beyvra_market_authority_data_age_seconds",
    "Canonical market data age",
    ("provider", "data_type", "asset_class", "environment"),
)
MARKET_DATA_STALE = Counter(
    "beyvra_market_authority_stale_total",
    "Canonical stale decisions",
    ("provider", "data_type", "asset_class", "environment"),
)
MARKET_SNAPSHOT_DISAGREEMENT = Counter(
    "beyvra_market_snapshot_disagreement_total",
    "Snapshot and stream disagreements",
    ("provider", "data_type", "asset_class", "environment"),
)
MARKET_FAILOVER = Counter(
    "beyvra_market_failover_total",
    "Observable provider failovers",
    ("provider", "data_type", "asset_class", "environment"),
)
DB_RETRIES = Counter(
    "beyvra_db_transaction_retries_total",
    "DB transaction retries",
    ("operation",),
)
DB_DEADLOCKS = Counter("beyvra_db_deadlocks_total", "DB deadlocks")
DB_ERRORS = Counter(
    "beyvra_db_connection_errors_total",
    "DB connection errors",
)
REDIS_ERRORS = Counter(
    "beyvra_redis_errors_total",
    "Redis errors",
    ("operation",),
)
REDIS_RECONNECTS = Counter(
    "beyvra_redis_reconnects_total",
    "Redis reconnects",
)
WORKER_UP = Gauge(
    "beyvra_worker_up",
    "Critical worker running",
    ("worker_type",),
)
WORKER_LAST_SUCCESS = Gauge(
    "beyvra_worker_last_success_timestamp_seconds",
    "Worker last successful operation",
    ("worker_type",),
)
WORKER_FAILURES = Counter(
    "beyvra_worker_failures_total",
    "Worker failures",
    ("worker_type", "failure_category"),
)
WORKER_RESTARTS = Counter(
    "beyvra_worker_restarts_total",
    "Worker process starts",
    ("worker_type",),
)
SAFETY_FLAGS = Gauge(
    "beyvra_safety_flag_enabled",
    "Safety-related feature flag",
    ("flag",),
)
CHAOS_FAULT = Gauge(
    "beyvra_chaos_fault_active",
    "Isolated chaos fault active",
    ("scenario",),
)
CHAOS_RECOVERY = Histogram(
    "beyvra_chaos_recovery_duration_seconds",
    "Isolated recovery duration",
    ("scenario",),
)
RECONCILIATION_RUNS = Counter(
    "beyvra_reconciliation_runs_total",
    "Reconciliation runs",
    ("status", "scope"),
)
RECONCILIATION_VIOLATIONS = Counter(
    "beyvra_reconciliation_violations_total",
    "Reconciliation violations",
    ("check_code", "severity"),
)
RECONCILIATION_LAST_SUCCESS = Gauge(
    "beyvra_reconciliation_last_success_timestamp_seconds",
    "Last successful reconciliation",
)

LIVE_EFFECT_CATEGORIES = (
    "broker_order_create",
    "broker_order_cancel",
    "custody_provider",
    "payment_provider",
    "transactional_email",
)
LIVE_EFFECT_RESULTS = ("attempt", "success", "failure")
LIVE_EFFECTS = Counter(
    "beyvra_live_effects_total",
    "Attempts to invoke an externally effectful production boundary",
    ("effect", "result"),
)

SAFETY_FLAG_NAMES = (
    "REAL_TRADING_ENABLED",
    "EXTERNAL_EXECUTION_ENABLED",
    "REAL_MONEY_ENABLED",
    "REAL_DEPOSITS_ENABLED",
    "REAL_WITHDRAWALS_ENABLED",
    "REAL_INTERNAL_TRANSFERS_ENABLED",
    "LIVE_BROKER_ROUTING_ENABLED",
    "FIX_LIVE_SESSION_ENABLED",
    "PAYMENTS_ENABLED",
    "TRANSACTIONAL_EMAIL_ENABLED",
    "WELCOME_EMAIL_ENABLED",
    "SIMULATED_TRADING_ENABLED",
    "REALTIME_V2_V1_FALLBACK_ENABLED",
)


def initialize_live_effect_metrics():
    """Publish explicit zero-valued series before any provider is invoked."""
    for effect in LIVE_EFFECT_CATEGORIES:
        for result in LIVE_EFFECT_RESULTS:
            LIVE_EFFECTS.labels(effect=effect, result=result).inc(0)


def record_live_effect(effect, result="attempt"):
    bounded_effect = effect if effect in LIVE_EFFECT_CATEGORIES else "payment_provider"
    bounded_result = result if result in LIVE_EFFECT_RESULTS else "failure"
    LIVE_EFFECTS.labels(effect=bounded_effect, result=bounded_result).inc()


def category(value):
    value = str(value or "unknown").lower()
    return (
        value
        if value
        in {
            "validation",
            "dependency",
            "timeout",
            "conflict",
            "internal",
            "unknown",
        }
        else "unknown"
    )


def worker_success(worker_type):
    WORKER_UP.labels(worker_type).set(1)
    WORKER_LAST_SUCCESS.labels(worker_type).set(time.time())


def set_safety_flags(settings):
    for name in SAFETY_FLAG_NAMES:
        SAFETY_FLAGS.labels(name.lower()).set(
            1 if getattr(settings, name, False) else 0
        )
    SAFETY_FLAGS.labels("deployment_read_only").set(
        1
        if os.getenv("DEPLOYMENT_READ_ONLY", "false").strip().lower()
        == "true"
        else 0
    )


@contextmanager
def timed(histogram, *labels):
    with histogram.labels(*labels).time() if labels else histogram.time():
        yield
