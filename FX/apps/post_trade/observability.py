from prometheus_client import Counter, Gauge, Histogram

TRADES_CAPTURED = Counter("beyvra_trades_captured_total", "Canonical trades captured", ("mode", "result"))
TRADE_CAPTURE_FAILURES = Counter("beyvra_trade_capture_failures_total", "Trade capture failures", ("reason",))
ALLOCATIONS = Counter("beyvra_trade_allocations_total", "Trade allocations", ("method",))
SETTLEMENT_INSTRUCTIONS = Counter("beyvra_settlement_instructions_total", "Settlement instructions", ("mode", "state"))
EXCEPTIONS_OPEN = Gauge("beyvra_post_trade_exceptions_open", "Open post-trade exceptions", ("severity",))
CONFIRMATIONS = Counter("beyvra_trade_confirmations_generated_total", "Trade confirmations", ("mode",))
RECONCILIATION_VIOLATIONS = Counter("beyvra_post_trade_reconciliation_violations_total", "Post-trade reconciliation violations", ("check",))
PROCESSING = Histogram("beyvra_post_trade_processing_seconds", "Post-trade processing latency", ("stage",))
SETTLEMENT_PENDING_AGE = Gauge("beyvra_settlement_pending_age_seconds", "Oldest pending settlement age", ("mode",))
