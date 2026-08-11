# CRM integrations (staging)

All endpoints are under `/api/v1/` and are disabled for real external delivery in staging. Service-to-service user creation uses a hashed `ServiceToken` and the `users:write` scope. Browser administration uses the existing session plus an organization membership.

`POST /users` requires `Authorization: Bearer <token>`, an `Idempotency-Key`, and terms consent. It rejects caller-controlled roles, permissions, balances, account types, and passwords. A successful request atomically creates a pending-activation user, one `DEMO` account, and one immutable `DEMO_INITIAL_CREDIT` ledger entry for `200000` cents. Demo funds are virtual USD only and cannot be withdrawn or transferred.

CRM inbound events use `/integrations/crm/{connection_id}/users` with `X-Codestra-Timestamp`, `X-Codestra-Event-Id`, and `X-Codestra-Signature-256`. The signature is `hex(HMAC-SHA256(secret, timestamp + "." + raw_body))`; timestamps older than five minutes and replayed event IDs are rejected.

CSV imports are upload, preview (`GET .../{id}/rows`), explicit commit, and cancel. Files are UTF-8 CSV, limited to 5 MiB/10,000 rows, and use the documented allowlist. Passwords, roles, balances, account types, API keys, and authentication secrets are never accepted. Commit processing is asynchronous and row results are retained for review.

CRM credentials are encrypted with a key derived from `SECRET_KEY`; secrets are write-only and redacted from API responses/logs. Endpoints must be HTTPS and DNS-resolve outside loopback, private, link-local, and metadata networks. CRM connections default disabled and reuse the existing signed webhook delivery/retry/dead-letter path.
