# Real Wallet Boundary Architecture

The `real_wallet` Django app is a separate financial boundary from the demo
wallet. It owns tenant-scoped wallets, atomic balances, immutable ledger
transactions, holds, deposits, withdrawals, transfers, provider receipts,
outbox events, audit records, webhook secrets, reconciliation runs, and feature
flags. It has no foreign keys to demo wallet tables.

PostgreSQL is authoritative. Redis is limited to cache, rate limiting, short
locks, and channel state. External custody, chain, compliance, and webhook
providers are represented by interfaces and fail-closed adapters.

Value-changing operations use a validate → lock → persist ledger/business state
and outbox → commit → asynchronous provider action sequence. Real-value flags
default to disabled and disabled endpoints return RFC-style problem details.

The private stream endpoint is `ws/v1/real-wallet/`, authenticated by the
existing one-time WebSocket ticket middleware. Stream events are versioned and
resume-aware; access tokens are not accepted in URLs.
