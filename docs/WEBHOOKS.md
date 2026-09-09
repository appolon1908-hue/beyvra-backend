# Beyvra notification webhooks

Webhook subscriptions are managed by the authenticated API under `/api/notification/webhooks/`.

## Delivery contract

Each delivery is a UTF-8 JSON `POST` with this shape:

```json
{
  "id": "event UUID",
  "type": "TRADE",
  "title": "Trade completed",
  "message": "Your trade was completed.",
  "payload": {},
  "created_at": "2026-08-03T17:00:00+00:00"
}
```

Headers:

- `Content-Type: application/json`
- `X-Codestra-Event: <type>`
- `X-Codestra-Signature-256: sha256=<lowercase HMAC-SHA256>`

The signature is calculated over the exact raw request body using the subscription secret. Receivers must compare it with a constant-time comparison and return any 2xx status to acknowledge delivery. Non-2xx responses and request timeouts are recorded as failed deliveries and retried by Celery with exponential backoff within an initial five-attempt budget.

The authenticated UI exposes create, edit, enable/disable, delete, test delivery, and delivery history. The staging-only receiver is `/api/notification/staging-receiver/`; it validates the signature and accepts `?status=500` for controlled retry tests. Its secret is configured outside Git via `STAGING_WEBHOOK_RECEIVER_SECRET`.

## Destination and retry safety

Outside DEBUG, registration and every delivery require HTTPS and public unicast
IPv4/IPv6 answers. Delivery checks every DNS answer, connects directly to one
validated numeric address, and retains the original Host header, TLS SNI and
certificate hostname verification. Environment proxies and redirects are not used.
Response bodies are not buffered. See the [urllib3 custom SNI documentation](https://urllib3.readthedocs.io/en/stable/advanced-usage.html#custom-sni-hostname).

A manual `POST /api/notification/webhooks/{subscription_id}/retry/` requires
`Idempotency-Key`, `X-Request-ID`, `If-Match: {status}:{attempts}`, and a JSON
object with a UUID string `delivery_id`. Invalid bodies return 400; a missing or
foreign delivery returns 404; stale versions return 409. Each accepted manual
retry grants at most five more attempts. `attempts` remains the lifetime count,
while `attempt_limit` exposes the current budget. Replaying the same command does
not grant another budget or queue another task. The lifetime limit is 32767;
once exhausted, manual retry returns 409. Existing deliveries migrate with an
initial limit of five, preserving their existing attempt counts.
