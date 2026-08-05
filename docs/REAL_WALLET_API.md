# Real Wallet API

The authoritative contract is
`contracts/openapi/codestra-real-wallet-v1.yaml`; the route inventory is
`contracts/openapi/real-wallet-endpoint-catalog.json`.

Implemented read boundaries include feature state, status, enabled assets and
networks, tenant-scoped wallets, balances, addresses, deposits, withdrawals,
webhook subscriptions, secret rotation, admin approval, and reconciliation.

Contract-only mutation and future-trading routes are explicitly registered and
return `FEATURE_DISABLED` until an approved activation. They never return fake
financial success. Value-changing requests require PostgreSQL idempotency and
an `Idempotency-Key` header when activated.

Errors use `application/problem+json` with stable `code`, `request_id`, and
`instance` fields. Atomic amounts are decimal strings, never JavaScript
numbers.
