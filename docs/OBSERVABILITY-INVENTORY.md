# Observability Inventory

Inventory combines repository inspection and read-only authorized-host checks on
2026-08-11. “Staged” means validated in the draft PR, not deployed.

| Capability | Classification | Evidence and action |
|---|---|---|
| Prometheus | ACTIVE | Existing v3.13 service ready; existing targets up. Canonical private scrape config staged. |
| Grafana | ACTIVE | Existing v13.1 health/database OK; legacy realtime dashboard plus five canonical dashboards staged. |
| Alertmanager | ACTIVE | Existing v0.28 ready; canonical routing/rules staged with credential-free receiver placeholder. |
| Django metrics | ACTIVE / DUPLICATE | `django-prometheus`, legacy `codestra_*`/`simulated_*`; retain compatibility and retire only after query audit. |
| PostgreSQL exporter | MISSING | Private exporter provisioning staged; reviewed least-privilege DSN secret required. |
| Redis exporter | MISSING | Private exporter provisioning staged; read-only password secret required. |
| NATS/JetStream | ACTIVE | Internal monitoring on 8222; private native exporter staged for varz/jsz. |
| Centrifugo | ACTIVE | Internal health and Prometheus endpoint enabled; private direct scrape staged. |
| Containers | ACTIVE | Existing cAdvisor target up; no container IDs used as application labels. |
| Nginx/Caddy | ACTIVE / SECURITY_RISK | Public catch-all existed; exact monitoring paths now return 404 in staged Nginx config. |
| Worker metrics | MISSING | Canonical up/last-success/failure/restart metrics now instrumented for critical workers. |
| Health probes | ACTIVE | `/health/live` process-only; `/health/ready` checks PostgreSQL/Redis and enabled NATS worker, not disabled providers. |
| Structured logs | ACTIVE | JSON formatter and correlation middleware exist; secret/raw-payload prohibition documented. |
| OpenTelemetry | MISSING | Not introduced because no existing collector/SDK and destabilization risk exceeds current benefit. |

High-cardinality risk audit: raw URLs and user, tenant, account, order, trade,
request, correlation, trace, event, session, channel, PID and container identifiers
are prohibited metric labels. `instrument` is omitted until a bounded approved catalog
exists. Controlled labels are enumerated state/status/decision/category/environment,
policy version, worker type, consumer type, provider and simulation.

Legacy retirement path: keep legacy collectors and dashboards for at least one full
staging observation window; prove no PromQL/dashboard/alert references; publish the
canonical replacement; then remove in a separately reviewed compatibility change.

Metrics, Prometheus, exporters, Alertmanager and Grafana have no published ports in
the staged Compose file. Grafana anonymous access and sign-up are disabled. Public
proxies must never route `/metrics`, `/prometheus/` or `/grafana/`.
