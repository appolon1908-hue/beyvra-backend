# Isolated staging integration certification — 2026-08-11

## Scope and safety boundary

This certification used disposable PostgreSQL 16, Redis, NATS JetStream,
backend, frontend, Prometheus, Grafana, and Financial Service containers. It
did not deploy to production or contact a custody, payment, or execution
provider. Synthetic accounts and data were used throughout.

The following server-authoritative flags remained false:

- `REAL_WALLET_READ_ENABLED`
- `REAL_DEPOSITS_ENABLED`
- `REAL_WITHDRAWALS_ENABLED`
- `REAL_INTERNAL_TRANSFERS_ENABLED`
- `REAL_TRADING_ENABLED`
- `EXTERNAL_EXECUTION_ENABLED`
- `REAL_MONEY_ENABLED`

## Results

| Gate | Result | Evidence |
| --- | --- | --- |
| Financial Service mTLS | PASS | Missing client certificate rejected; valid synthetic client certificate accepted. |
| Reservation/release/settlement contract | PASS | PostgreSQL 16 rollback-only invariant exercise covered reserve, release, capture, idempotency, outbox/inbox, and reconciliation. |
| Financial routes fail closed | PASS | Wallet/deposit/withdrawal reads and all tested money mutation routes returned `503 FEATURE_DISABLED`; no provider request was emitted. |
| Integrated browser E2E | PASS | 42 passed, 2 policy-dependent flows skipped, 0 failed. |
| Compliance and operator E2E | PASS | RBAC, tenant separation, maker/checker, self-approval denial, safe errors, and audit timeline covered by API and browser suites. |
| Realtime reconnect and gap recovery | PASS | Reconnect obtains a fresh server-issued ticket; a sequence gap triggers snapshot recovery before ordered dispatch. |
| Prometheus/Grafana runtime | PASS | Backend target up; four rule groups and 25 rules loaded; provisioned dashboard healthy. |
| Full-stack restore | PASS | Private custom-format database backup restored to fresh PostgreSQL 16; backend readiness, restored synthetic API data, and frontend artifact verified. |
| PITR | PASS | Base backup plus WAL replay recovered the pre-target row and excluded the post-target row before promotion. |
| Chaos baseline | PASS | PostgreSQL and Redis fail safely and recover; a committed order during NATS interruption settled after publisher/consumer recovery without duplicate effect. |

The browser skips were deliberate: the demo vertical slice refuses to invent a
market quote when no certified quote is available, and webhook management
requires an independently verified fixture. Neither skip enables a financial
path.

The isolated browser environment raised user and anonymous request-rate
thresholds solely to prevent the shared synthetic fixture from exhausting a
normal per-user budget across the complete suite. Rate limiting remained
enabled and has separate contract tests. No production configuration changed.

## Database and supply-chain checks

- Migration from zero, rollback, reapply, and drift checks passed on PostgreSQL 16.
- Backend and rebuilt Financial Service images had zero fixed critical findings under the configured Trivy gate.
- Current-source secret scans passed. Historical backend commits retain known findings and are not certified as history-clean.
- The Financial Service image excludes local TLS material through `.dockerignore`.
- CycloneDX SBOM evidence was generated for the backend integration image.

## Evidence location

Machine-readable results, checksums, backup/restore output, PITR output, and
observability results are stored outside the repository at:

`/root/beyvra-isolated-staging-cert-20260811T124814Z/`

The evidence contains synthetic test artifacts only and is not a production
backup.

## Remaining independent actions

- Review and merge remain repository-owner actions.
- Provider activation, real-money activation, production deployment, and any
  compliance or legal policy approval remain explicitly out of scope.
