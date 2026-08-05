# Real wallet and ledger boundary

The `real_wallet` Django app is a separate financial boundary. It does not
reference the legacy `wallet` app, demo accounts, demo refills, paper-trading
balances, or simulated settlement code.

All real-value feature flags default to disabled. Disabled endpoints return a
stable RFC-style `FEATURE_DISABLED` problem response and never return fake
financial success. PostgreSQL is the source of truth; Redis is not used by
this boundary for balances, ledger state, or idempotency.

## Current implementation

The foundation includes separate asset, network, wallet, balance, immutable
ledger, hold, idempotency, outbox, deposit, withdrawal, transfer, feature flag,
and audit tables. Atomic amounts use `NUMERIC(78,0)` through Django
`DecimalField(max_digits=78, decimal_places=0)`. Ledger posting validates
single-asset balance and PostgreSQL installs a guard against mutating posted
entries.

Provider-neutral custody and chain protocols are defined in
`FX/real_wallet/providers.py`; default adapters fail closed. Webhook secrets
use AES-256-GCM with a protected 32-byte key file, and webhook destinations are
HTTPS-only with checks against private, loopback, link-local, reserved, and
unspecified addresses. Inbound event receipts are tenant-scoped and
deduplicated by event ID.

`reserve_idempotency`, `enqueue_outbox`, and `create_webhook_delivery` provide
database-backed request reservation, transactional outbox persistence, and
at-least-once delivery deduplication primitives. They do not call brokers,
custody systems, blockchain nodes, or customer endpoints synchronously.

The initial API boundary is intentionally disabled. Custody, chain, compliance,
MFA, provider webhook, reconciliation, and production activation require
separate reviewed implementations and credentials. No private-key handling is
implemented or permitted.

Read-only wallet and balance routes are implemented with authenticated,
tenant-scoped queries. They return data only when `real_wallet_read_enabled` is
explicitly enabled; all value-changing routes remain disabled.

Reference configuration endpoints expose only enabled assets, networks, and
asset/network pairs. Feature-state output contains booleans only and never
includes provider credentials or infrastructure details.

The withdrawal domain service now validates an active, cleared, non-cooling
withdrawal address, reserves funds with a database hold, persists a
`REQUESTED` withdrawal, records an outbox event, and completes idempotency in a
single transaction when `real_wallet_withdrawals_enabled` is explicitly
enabled. It never signs, broadcasts, or calls a custody provider.

Webhook subscriptions can be listed or created for the caller's first active
organization membership. Creation validates HTTPS destinations against SSRF
targets, stores only encrypted secret material, and returns the generated
secret once. Subscription delivery remains disabled until an independently
reviewed delivery worker and activation policy exist.

Secret rotation creates a new encrypted key version and gives the prior
version a one-hour overlap window before expiry. The replacement secret is
returned once; plaintext secrets are never returned from read endpoints.

Internal transfers are implemented as a gated service with deterministic
balance locking, same-tenant wallet checks, a balanced ledger transaction,
projection updates, idempotency, and an outbox event. They do not create a
blockchain transaction.

Deposit detection and crediting are also implemented behind
`real_wallet_deposits_enabled`. Chain events are deduplicated by asset-network,
transaction hash, and output index; crediting requires the configured
confirmation threshold, posts a balanced ledger transaction, updates the
balance projection, and emits an outbox event in one transaction.

Withdrawal cancellation, failure recovery, and completion are implemented as
idempotent lifecycle services. Cancellation/failure releases an active hold;
completion captures it, posts the customer-to-platform ledger transaction,
records the blockchain reference, and emits the corresponding event. Custody
signing and broadcast remain outside the application and disabled.

## Migration

Run `python manage.py migrate real_wallet`. The migration creates only tables
prefixed `real_wallet_` and `real_ledger_`; it does not alter legacy demo
wallet tables. Deployment should place these tables in the approved isolated
financial schema/database before enabling any feature flag.
