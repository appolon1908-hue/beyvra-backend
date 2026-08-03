# Codestra notification webhooks

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

The signature is calculated over the exact raw request body using the subscription secret. Receivers must compare it with a constant-time comparison and return any 2xx status to acknowledge delivery. Non-2xx responses and request timeouts are recorded as failed deliveries and retried by Celery with exponential backoff (up to five retries).

The authenticated UI exposes create, edit, enable/disable, delete, test delivery, and delivery history. The staging-only receiver is `/api/notification/staging-receiver/`; it validates the signature and accepts `?status=500` for controlled retry tests. Its secret is configured outside Git via `STAGING_WEBHOOK_RECEIVER_SECRET`.
