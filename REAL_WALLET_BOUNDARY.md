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

The initial API boundary is intentionally disabled. Custody, chain, compliance,
MFA, provider webhook, reconciliation, and production activation require
separate reviewed implementations and credentials. No private-key handling is
implemented or permitted.

## Migration

Run `python manage.py migrate real_wallet`. The migration creates only tables
prefixed `real_wallet_` and `real_ledger_`; it does not alter legacy demo
wallet tables. Deployment should place these tables in the approved isolated
financial schema/database before enabling any feature flag.
