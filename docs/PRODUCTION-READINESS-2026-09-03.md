# Beyvra backend production-readiness review — 2026-09-03

## Decision

This repository is prepared as a **read-only production candidate**, not an
active-money release. The candidate deliberately disables simulation workers,
live broker routing, real-money execution, payments, transactional email, and
all state-changing HTTP requests at the edge.

Production activation remains **NO-GO** until this candidate is merged, built
from protected `main`, certified in `staging-readonly`, rollback is rehearsed,
and the same image digests are promoted to `production-readonly`.

## What this candidate fixes

| Area | Candidate state |
| --- | --- |
| Source authority | Clean branch created from the exact protected `main` SHA |
| OpenAPI | Runtime dates no longer make the generated contract change by day |
| Outbox liveness | Idle healthy workers refresh liveness; dead letters remain fail-closed |
| Realtime probe | Uses a valid RFC 6455 nonce and the real Centrifugo WebSocket route |
| Runtime identity | `/api/v1/system/version` exposes source SHA, image digest, environment, and safety flags |
| Web restarts | Steady-state web startup no longer runs migrations or `collectstatic` |
| Schema changes | One-shot release initialization blocks pending migrations unless explicitly approved |
| Container promotion | Production Compose accepts only immutable `repository@sha256` images and never builds |
| Read-only canary | Nginx allows only `GET`, `HEAD`, and `OPTIONS`; mutations return `DEPLOYMENT_READ_ONLY` |
| Backups | Custom-format dump, restore-list validation, checksum, and required off-host copy |
| Rollback | Deployment captures the complete previous image tuple and automatically restores it on failure |
| Supply chain | Source labels, SBOM/provenance publication, high/critical image scanning, and pinned direct dependencies |
| Scheduler startup | Celery Beat periodic-task setup waits until its schema is fully migrated |

## Deliberately excluded from this candidate

The following work must stay separate because it changes financial data or
enables state-changing operations:

1. Bank-account identifier encryption and its data migration.
2. Active operator/admin command hardening and durable idempotency for every
   financial mutation.
3. Live broker credentials, live trading, real money, deposits, withdrawals,
   payments, transactional email, and background execution workers.
4. Any production schema migration that has not passed expand/contract
   compatibility review and restore rehearsal.

## Required evidence before production-readonly

The `staging-readonly` protected environment must produce:

- exact source SHA and backend/edge image digests;
- successful `health/live`, `health/ready`, version, capabilities, and
  non-destructive API certification;
- proof that every state-changing request is rejected at the edge;
- database backup plus checksum and off-host copy;
- migration plan and an explicit zero-migration result unless migration
  approval was granted;
- complete running image inventory;
- rollback to the previous exact image tuple with identity readback;
- no movement in live-money, external-execution, payment, email, or trading
  counters.

Only the same staging-certified backend and edge digests may be supplied to the
`production-readonly` environment. Production image rebuilding is rejected by
the workflow.

## Current repository verdict

**Repository candidate: READY FOR PROTECTED PR REVIEW**

**Staging certification: NOT YET EXECUTED**

**Production-readonly deployment: NOT YET EXECUTED**

**Active trading / real money: NOT AUTHORIZED**
