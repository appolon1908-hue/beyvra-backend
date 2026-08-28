# Webhook Security Specification

## Security Controls & Ingestion Pipeline

All external provider webhooks (executions, market-data, custody) must pass through standard pipeline controls:

```
Provider Webhook Request
         │
         ▼
┌─────────────────────────┐
│ 1. Body Size (< 1MB)    │
│ 2. Provider Allowlist   │
│ 3. HMAC-SHA256 Signature│
│ 4. Replay Window (<300s)│
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐   Duplicate   ┌───────────────────────────┐
│ Durable Inbox Check     ├──────────────►│ Return 200 OK (No Action) │
│ UNIQUE(provider, ext_id)│               └───────────────────────────┘
└───────────┬─────────────┘
            ▼ New Event
┌─────────────────────────┐
│ Return 202 Accepted     │
└───────────┬─────────────┘
            ▼
┌─────────────────────────────────────────┐
│ Asynchronous Worker Processing          │
│ ├── Apply to Canonical Domain Model     │
│ ├── Write Immutable Events              │
│ ├── Transactional Outbox Publish        │
│ └── Mark Processed in Inbox             │
└─────────────────────────────────────────┘
```

## Replay Attack Protection
1. `X-Timestamp`: Checked against system clock (`abs(now - timestamp) <= 300` seconds).
2. `X-Signature`: HMAC SHA-256 computed over `timestamp.event_id.provider_id.raw_body` using constant-time comparison `hmac.compare_digest`.
3. `Durable Inbox Deduplication`: Primary key / unique constraint on `(provider, provider_event_id)` ensures idempotent processing.
