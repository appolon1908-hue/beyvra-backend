# Disaster recovery runbook

This runbook is limited to isolated/staging Beyvra simulation. Production restore and Financial PostgreSQL are outside authorization.

## Detect and classify

Declare severity and record incident time, affected tenant scopes, last known-good commit/image, database timeline and backup/checksum identifiers. `SEV1` means state-integrity risk, a duplicate settlement, or loss of committed trading state. `SEV2` is a major staging/application outage without evidence of corruption. `SEV3` is degraded recovery capability or a stale/failed backup. `SEV4` is a low-impact documentation or monitoring defect. Page the service owner for SEV1/SEV2; notify operations for SEV3; track SEV4 normally.

## Contain and freeze writes

1. Preserve reads, health probes, audit and reconciliation.
2. Set the tested platform `TradingControl` to `CANCEL_ONLY` or `MAINTENANCE` using the existing authenticated admin control. Prefer `CANCEL_ONLY` only when cancellation is verified safe for the failure mode.
3. Stop simulated order consumers and outbox publishers only after recording their durable state. Do not delete messages or database rows.
4. Confirm all real/external/money flags remain false. A missing required secret must fail closed; never use a historical or hardcoded credential.
5. Capture logs, database timeline, current commit/image digests and sanitized configuration hashes.

There is deliberately no untested global kill-switch script. Two-person review is required before resuming mutation after a SEV1 integrity event.

## Back up, restore and reconcile

Run the disposable verifier from a clean checkout:

```sh
BEYVRA_DR_ISOLATED=1 \
REAL_TRADING_ENABLED=false \
EXTERNAL_EXECUTION_ENABLED=false \
REAL_MONEY_ENABLED=false \
./scripts/disaster-recovery-verify.sh
```

For a staging incident, verify the SHA-256 before restore, create a new isolated network/database, restore without attaching applications, inspect `pg_restore --list`, apply migrations only after compatibility review, and run full reconciliation. Do not resume on a non-zero invariant.

## Validate and resume

Validate liveness/readiness, login, preview, full/partial fills, cancellation, positions, wallet projection, `/ws/v2/` reconnect/snapshot/gap recovery, cross-tenant denial, outbox draining and duplicate redelivery. Validate Prometheus targets, dashboards, alerts and workers. Compare API/order p95, outbox lag and realtime reconnect with the pre-incident baseline. Append a post-restore audit event. Resume consumers before opening mutations, then remove the freeze with two-person review for SEV1.

## Rollback and configuration recovery

Validate Caddy/nginx and NATS configuration before activation. A controlled bad candidate must be deployed only through the staging deployment controller, detected by health gates, and rolled back to a recorded digest. A migration failure is recovered in a disposable database first; never assume reverse migrations are safe. These live-controller exercises are not certified by the repository-only verifier.

## Authorization matrix

| Action | Autonomous | Approval required |
|---|---:|---|
| Run disposable local verifier | Yes | No |
| Restore into a new isolated staging database | Yes | No, within this mission |
| Attach staging applications or resume writes | No | Staging service owner |
| Delete retained backups | No | Data owner and approved retention policy |
| Restore production | No | Production incident commander/change authority |
| Read, back up or restore Financial PostgreSQL | Never in this runbook | Financial Service authority only |
| Enable a provider or real-money/external execution | Never in this runbook | Protected-control authority |

## Post-incident review

Record timeline, RPO/RTO, cause, evidence identifiers, invariant results, customer/tenant impact, manual steps, corrective actions and owners. Redact secrets and backup contents.

