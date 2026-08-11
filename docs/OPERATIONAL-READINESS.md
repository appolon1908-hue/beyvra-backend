# Operational Readiness Status

The backend control-plane artifacts are ready for review: canonical metrics, private
scrape/rules/routing configuration, five dashboards, SLI/SLO definitions, immutable
read-only reconciliation, real disposable-service fault certification, deterministic
load tooling, security hardening and runbooks.

The pre-change rollback backup is
`/root/backups/beyvra-operational-readiness-20260811T075504Z` with SHA-256 manifest.
No secret values or Financial Service data are included.

Read-only staging validation found the home and canonical API reachable, internal
backend liveness/readiness healthy, workers running without restarts, and the existing
Prometheus/Grafana/Alertmanager services ready. Existing Prometheus targets were up,
but did not yet include the new backend/PostgreSQL/Redis/NATS/Centrifugo targets.
Therefore the new dashboards and alerts are validated artifacts, not deployed claims.
Public `/metrics` resolves to frontend HTML; application metrics remain internal.

Deployment gate: review the stacked draft PRs, provision exporter credentials through
approved secrets, configure authenticated Grafana and reviewed Alertmanager receivers,
apply the reconciliation migration, schedule the gauge refresher/reconciliation,
then perform a rollback-ready observability-only deployment. Staging chaos remains prohibited.
