# Disaster-recovery certification result

Run date: 2026-08-11 UTC. Starting head: `4d369df1363174cc1088728d3a006ccce840487d`. Scope: disposable, internal-network resources only.

## Proven

- PostgreSQL 16 custom archive creation, SHA-256, archive parsing and restore into a fresh database.
- Schema, rows, functions, triggers, indexes and constraints were present after restore.
- Two committed simulated orders and two committed outbox rows survived; duplicate trades/settlements, reservation leaks and tested accounting errors were zero.
- The restored processed-event uniqueness constraint made a duplicate delivery a single business effect.
- Complete Redis loss did not alter authoritative PostgreSQL rows.
- A restored pending application outbox row published through JetStream. An unacknowledged durable-consumer delivery survived the NATS restart, redelivered, acknowledged, and the stream retained exactly one business event.
- The actual Django migration ledger was backed up and restored. The restored application passed system checks and both liveness/readiness endpoints.
- A failed transactional migration candidate left no partial relation. A missing required secret failed closed and the known-good application configuration recovered.
- Pre-backup audit rows survived, audit mutation was rejected by the restored trigger, and a post-restore event appended.
- Real/external/money flags were fail-closed at the verifier boundary; no production or Financial Service connection was used.
- RPO target 300 seconds; deterministic fixture RPO observed 0 seconds. RTO target 1800 seconds; the final exact-tree measurement is recorded in `latest/results.env`.
- Gitleaks found zero current-source secrets. Filesystem dependency scan found zero known vulnerabilities. Filesystem and application-image CycloneDX SBOMs were generated.
- The recovery PostgreSQL image runs as the unprivileged `postgres` user without the unused vulnerable privilege-drop helper; NATS was upgraded to 2.11. Trivy found zero critical vulnerabilities across the backend, PostgreSQL, Redis and NATS images.
- GitHub CI passed secret scanning, the Django/PostgreSQL validation suite (including simulated trading E2E, tenant isolation and websocket v2 tests), exact head/base verification, and the application-image critical/high scan.

## Not certified / blockers

- PITR has no WAL archive configuration and is a documented gap.
- No authorized live staging endpoint/deployment controller or frontend checkout was provided, so frontend reconnect/snapshot gap recovery, a real staging rollout rollback, runtime performance, Prometheus targets, Grafana and loaded-alert runtime state were not tested. The disposable backend host rebuild and controlled bad-config rollback passed, but do not establish production commitments.
- Backup encryption at rest and external backup-store ACLs cannot be inferred from a repository-only disposable file. Local artifact permissions were `0700/0600`, with no published backup.

`FINAL_STATUS=BLOCKED` only on the remaining environment-dependent frontend, realtime-gap, live monitoring/performance and true staging rollback drills. All repository-local and disposable-backend gates now pass; no critical container finding remains.
