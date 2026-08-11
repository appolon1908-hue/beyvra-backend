# Settlement contract

`settle_trade` carries `trade_ref`, `reservation_ref`, `account_ref`, asset legs, fee components, `executed_at`, idempotency key and correlation ID. Financial Service owns validation and posting. Duplicate requests have one effect.

No live settlement is enabled. A timeout, connection loss, late response, duplicate response, or restart leaves the application in an explicit unknown state. It must query the operation by reference/key; unknown is never presented as success and blind retry is forbidden.
