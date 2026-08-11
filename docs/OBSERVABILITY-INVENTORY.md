# Observability Inventory

| Capability | Current state | Gap / action |
|---|---|---|
| PROMETHEUS | `django-prometheus` exposes `/metrics`; new private scrape config staged | No deployed server found in repository |
| GRAFANA | One legacy realtime JSON | Five canonical provisionable dashboards added |
| ALERTMANAGER | No prior config | Safe placeholder routing added; operator receiver must be configured out-of-band |
| POSTGRES_EXPORTER | Absent | Private scrape target defined; deployment image/credential secret still required |
| REDIS_EXPORTER | Absent | Private scrape target defined; deployment wiring still required |
| NATS_METRICS | Internal monitoring on 8222 | Exporter scrape target defined; native metrics retained |
| CENTRIFUGO_METRICS | Enabled internally at `/metrics` | Direct private scrape retained |
| CONTAINER_METRICS | Absent | Add authenticated/private cAdvisor only after host approval |

Existing `codestra_*`, `simulated_*`, and django-prometheus metrics remain compatible.
Canonical `beyvra_*` metrics are additive. Existing alerts cover nginx upstreams,
integrations, and realtime. Missing areas were trading state, outbox age, idempotency,
invariants, worker state, safety flags, DB/Redis application failures, and chaos recovery.

Metric labels are bounded enums or controlled worker/consumer types. Raw URLs and
user, order, trade, request, correlation, account, private channel, PID, and container
identifiers are prohibited. `instrument` remains absent because its approved bounded
catalog is not yet enforced. Correlation belongs in logs/traces, never metric labels.

Metrics are internal in Docker networking. Nginx must not proxy `/metrics`, Prometheus,
Grafana, exporter, NATS monitoring, or Centrifugo metrics endpoints publicly.
OpenTelemetry was not present and is intentionally deferred to avoid destabilization.
