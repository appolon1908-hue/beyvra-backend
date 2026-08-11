# Disaster-recovery certification result

Run date: 2026-08-11 UTC. Starting head: `4d369df1363174cc1088728d3a006ccce840487d`. Scope: disposable, internal-network resources only.

## Proven

- PostgreSQL 16 custom archive creation, SHA-256, archive parsing and restore into a fresh database.
- Schema, rows, functions, triggers, indexes and constraints were present after restore.
- Two committed simulated orders and two committed outbox rows survived; duplicate trades/settlements, reservation leaks and tested accounting errors were zero.
- The restored processed-event uniqueness constraint made a duplicate delivery a single business effect.
- Complete Redis loss did not alter authoritative PostgreSQL rows.
- Isolated NATS with JetStream enabled restarted healthy. This did not prove durable consumer position recovery or a business-event replay.
- Pre-backup audit rows survived, audit mutation was rejected by the restored trigger, and a post-restore event appended.
- Real/external/money flags were fail-closed at the verifier boundary; no production or Financial Service connection was used.
- RPO target 300 seconds; deterministic fixture RPO observed 0 seconds. RTO target 1800 seconds; isolated restore drill observed 8 seconds.
- Gitleaks found zero current-source secrets. Filesystem dependency scan found zero known vulnerabilities. A CycloneDX SBOM contains 44 components.

## Not certified / blockers

- PITR has no WAL archive configuration and is a documented gap.
- No authorized live staging endpoint/deployment controller or frontend checkout was provided, so application health, `/ws/v2/` gap recovery, host rebuild, deployment rollback, migration-failure recovery, config activation rollback, tenant-isolation E2E, restored-system E2E, runtime performance, Prometheus targets, Grafana and loaded alerts were not tested.
- Outbox rows survived, but an actual restored publisher drain and business consumer were not run. JetStream durable positions/replay are therefore not certified.
- Trivy found four critical vulnerabilities in current upstream recovery images: OpenSSL CVE-2026-31789 in `nats:2.10-alpine` (two packages) and Go stdlib CVE-2025-68121 in `nats:2.10-alpine` and `postgres:16-alpine`. Published fixed versions exist, so `CONTAINER_CRITICAL=0` is blocked.
- Backup encryption at rest and external backup-store ACLs cannot be inferred from a repository-only disposable file. Local artifact permissions were `0700/0600`, with no published backup.

`FINAL_STATUS=BLOCKED` until the critical container findings are removed and the untested staging/application drills are executed in an authorized isolated staging environment.

