# Beyvra disaster-recovery inventory

Scope: isolated staging simulation only. This is an engineering recovery target, not a production or Financial Service commitment.

## State classification

| Surface | Classification | Recovery rule |
|---|---|---|
| PostgreSQL 16 | AUTHORITATIVE_STATE | Back up and restore schema, migration history, orders, executions/trades, positions, simulated accounts/reservations/settlements, outbox, processed-event inbox, audit and reconciliation rows. |
| Redis | CACHE / DERIVED_STATE | Recreate empty. Sessions and websocket presence may be lost; users reauthenticate and clients fetch a canonical snapshot. Never reconstruct trading state from Redis. |
| NATS / JetStream | DERIVED_STATE / DELIVERY_STATE | Recreate streams and durable consumers from versioned configuration. PostgreSQL outbox is the publication authority; processed-event rows enforce business idempotency. |
| Centrifugo / realtime bridge | REBUILDABLE | Recreate from image/config; clients reconnect, fetch canonical PostgreSQL-backed state, then resume `/ws/v2/`. |
| backend, frontend, workers, execution consumer | REBUILDABLE | Restore immutable known-good images/repository revision. No mutable business authority may live in a container filesystem. |
| Caddy/nginx, Docker Compose, Prometheus, Grafana, systemd | CONFIGURATION | Restore from version control and validate before activation. |
| environment configuration and feature flags | CONFIGURATION / SECRET_MATERIAL | Restore sanitized names/hashes from evidence; retrieve values from the approved secret store. Never put values in backups or documentation. |
| provider credentials, database passwords, signing keys | SECRET_MATERIAL | Not present in the evidence package. Rotation/retrieval requires the owning authority. |

## Authoritative survival set

Committed simulated orders, executions, trades, positions, reservations, settlements, wallet projections, outbox events, processed-event inbox rows, audit events, reconciliation records and Django migration state must survive. PostgreSQL constraints, functions, triggers and indexes are part of that state.

Rebuildable state includes caches, sessions, websocket subscriptions, ephemeral NATS connections, container instances and rendered dashboards. JetStream delivery state should be recovered when available, but replay from the PostgreSQL outbox plus inbox idempotency is the correctness backstop. Redis is never authoritative for orders, balances, reservations, trades or settlements.

## Targets

- `RPO_TARGET_SECONDS=300` for isolated staging engineering drills.
- `RTO_TARGET_SECONDS=1800` for an isolated database/service rebuild.
- Observed RPO is the interval between the last committed fixture transaction and backup completion. The disposable deterministic drill has `RPO_OBSERVED_SECONDS=0`; this does not establish a production guarantee.
- Observed RTO is emitted by `scripts/disaster-recovery-verify.sh`.

## PITR readiness

The repository does not configure `archive_mode`, `archive_command`, WAL retention, an archive repository, or recovery-target automation. `PITR_READINESS=DOCUMENTED_GAP`. Enabling an archive destination is an infrastructure and retention decision and is intentionally not invented by this repository-only drill. The minimum follow-up is an encrypted, access-controlled WAL archive plus a scheduled isolated recovery-to-timestamp test.

## Retention and access

Proposed, not automatically enforced: 14 daily, 8 weekly, and 12 monthly verified backups. Existing backups must not be deleted until an owner approves policy and legal requirements. Disposable drill artifacts are mode `0600` inside a mode `0700` local directory and are removed manually; they are not published or committed. Any encryption status outside this harness must be verified at the storage layer and is currently unclaimed.

