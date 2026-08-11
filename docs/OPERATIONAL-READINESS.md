# Operational Readiness Status

The backend control-plane artifacts are ready for review: canonical metrics, private
scrape/rules/routing configuration, five dashboards, SLI/SLO definitions, immutable
read-only reconciliation, real disposable-service fault certification, deterministic
load tooling, security hardening and runbooks.

The original readiness backup is
`/root/backups/beyvra-operational-readiness-20260811T075504Z`. The immediate
pre-deployment rollback backup is
`/root/backups/beyvra-observability-deploy-20260811T124243Z`. Both have SHA-256
manifests.
No secret values or Financial Service data are included.

The rollback-ready observability-only deployment completed on 2026-08-11. Prometheus
now scrapes the backend, PostgreSQL exporter, Redis exporter, NATS exporter,
Centrifugo and readiness probe; all six targets were `UP`. Five Beyvra dashboards
loaded in authenticated Grafana, 20 alert rules loaded, and zero Beyvra alerts were
active. Node exporter and cAdvisor supply host/container CPU and memory. Exporters
expose no host ports and Prometheus remains on internal Docker networks. Public
`/metrics` still resolves to frontend HTML rather than internal metrics.

The isolated 10,000-workflow profile completed with zero errors and reconciliation
PASS, but order p95 was 2532.9 ms. Capacity certification therefore recommends no
more than 10 concurrent simulated workflow workers. A subsequent 1,000-workflow
concurrency-10 retest passed at 534.1 ms
order p95 with zero errors and reconciliation PASS, validating that guardrail for
isolated workloads. Repository-wide mypy passes 388 non-migration modules under a
documented legacy diagnostic ratchet.

Remaining gates: merge only through protected review, apply the reconciliation
migration with rollback, schedule gauge refresh/reconciliation, tighten the mypy
ratchet, tune the order pipeline, and migrate browser tokens to backend-managed
HttpOnly storage. Staging chaos remains prohibited.
