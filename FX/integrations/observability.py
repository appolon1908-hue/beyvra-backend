from prometheus_client import Counter, Gauge

USER_CREATE_TOTAL = Counter("codestra_user_create_total", "User creation outcomes", ["status"])
IMPORT_ROWS_TOTAL = Counter("codestra_import_rows_total", "Import row outcomes", ["status"])
CRM_DELIVERY_TOTAL = Counter("codestra_crm_delivery_total", "CRM delivery outcomes", ["status"])
WEBHOOK_DELIVERY_TOTAL = Counter("codestra_webhook_delivery_total", "Webhook delivery outcomes", ["status"])
INVALID_SIGNATURE_TOTAL = Counter("codestra_invalid_signature_total", "Rejected signatures", ["kind"])
DEMO_LEDGER_RECONCILIATION_FAILURE = Counter("codestra_demo_ledger_reconciliation_failure_total", "Ledger reconciliation failures")
IMPORT_QUEUE_DEPTH = Gauge("codestra_import_queue_depth", "Queued imports")


def count(metric, status="ok"):
    try:
        metric.labels(status=status).inc()
    except (AttributeError, ValueError):
        metric.inc()
