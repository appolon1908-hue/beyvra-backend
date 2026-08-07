# Backend P0 consolidation

## Authority boundaries

- Real trading contract: `/api/v1/trading/**`; every mutation fails closed with
  `FEATURE_DISABLED` while `REAL_TRADING_ENABLED=false`.
- Demo trading remains the existing isolated demo engine.
- Market authority remains the normalized `/api/v1/market/**` contract.
- Real value remains authoritative only in the independently deployed Financial
  Service. This application has one application database alias, rejects
  Financial PostgreSQL environment credentials, and provides no Financial
  Service mutation transport while P0 flags are disabled.
- Customer realtime remains the existing NATS/JetStream, bridge, Centrifugo,
  `/ws/v2/` path. No socket stack was added.
- News and calendar providers remain governance-disabled and 5-second candles
  remain unavailable.

Database feature flags cannot override the application-level real-wallet kill
switches. The legacy real-wallet implementation is retained for migration
compatibility but is not an authoritative real-money boundary.

## P0 primitives

`foundation.OutboxEvent` is the canonical application outbox for new
authoritative events. It uses transactional creation, concurrent claiming,
publish confirmation, retry/backoff, dead-letter state, and JetStream message
deduplication IDs. `ProcessedEvent` provides per-consumer idempotency and
`IdempotencyRecord` provides request replay/conflict semantics.

`ApplicationAuditEvent` is append-only in the model and PostgreSQL through an
update/delete rejection trigger. Trading controls are scoped, RBAC-protected,
reasoned, request-ID-addressed, idempotent, and audited.

The explicit spot order transition matrix, persisted order repository, risk
engine, disabled execution provider, and disabled Financial Service client form
the future order pipeline without activating execution or settlement.

## Local certification evidence

- Route resolver inventory: 594 HTTP patterns; see
  `API-CONSOLIDATION-INVENTORY.md`.
- Full Django suite: the final count and result are recorded in the release
  report; intermediate runs are not release evidence.
- Focused P0, compatibility, and repaired WebSocket regression suite: 19 tests
  passed on the final source before the release report was prepared.
- Migration drift: none.
- Fresh isolated PostgreSQL migration apply, rollback, data-preservation check,
  reapply, and database-enforced audit immutability: passed.
- Restored-backup migration lifecycle: must be recorded by the final gate; do
  not infer it from the fresh-database migration lifecycle.
- P0 changed-content secret scan: zero findings.
- Trivy dependency filesystem scan: zero vulnerability findings.

## Retained migration work

Legacy demo, email, and disabled real-wallet subsystems retain specialized
compatibility outbox/idempotency tables because their consumers and envelopes
cannot be removed without a coordinated migration. New authoritative code must
use `foundation.OutboxEvent`, the standard envelope, and
`foundation.IdempotencyRecord`. Removal of the legacy tables requires consumer
cutover evidence and is not performed opportunistically in P0.

The legacy route surface is retained and classified rather than deleted. Usage
metrics and deprecation headers provide the evidence required for later removal.
