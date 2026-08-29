# Beyvra Observability And Secrets Integration

This pack is the Beyvra-specific bridge into the Codestra observability and OpenBao repositories.
It contains deployable templates and wiring notes only. Secrets, provider keys, SMTP passwords,
Keycloak client secrets, and OpenBao root or recovery material must stay out of git.

## Local Repository Map

| Capability | Codestra repository | Beyvra integration status |
| --- | --- | --- |
| Grafana | `Codestra-Grafana-` | Provision Prometheus, Loki, and Tempo datasources from `grafana/datasources.yml`. Add Beyvra dashboards for API, auth/email, realtime, trading, DB, Redis, and public intake. |
| Prometheus | `Codestra-Prometheus` | Add `prometheus/beyvra-scrape.yml` and `prometheus/beyvra-alerts.yml` to the Prometheus deployment. |
| Alertmanager | `Codestra-Alertmanager` | Route Beyvra alert labels by `service`, `environment`, and `severity`. |
| Loki | `Codestra-Loki` | Receive structured backend logs through Alloy. |
| Tempo | `Codestra-Tempo` | Receive OTLP traces from Alloy or the OpenTelemetry collector after backend tracing is enabled. |
| OpenTelemetry | `Codestra-Telemetry` | Collector target for OTLP metrics/traces/logs when deployment uses collector instead of Alloy-only. |
| Superset | `Superset` | Use read-only analytics credentials only; do not connect with application owner credentials. |
| Node Exporter | `Codestra-Node-Exporter` | Host-level CPU, memory, disk, and network metrics. |
| cAdvisor | `Codestra-cAdvisor` | Container CPU, memory, restart, filesystem, and network metrics. |
| PostgreSQL Exporter | `Codestra-Postgres-Exporter` | PostgreSQL availability, connection, transaction, lock, table, and index metrics. |
| Redis Exporter | `Codestra-Redis-Exporter` | Redis availability, memory, evictions, connected clients, and command latency. |
| Blackbox Exporter | `Codestra-Blackbox-Exporter` | External HTTP probes from `blackbox/beyvra-probes.yml`. |
| Grafana Alloy | `Codestra-Alloy` | Collect Docker logs and scrape Beyvra metrics from `alloy/beyvra.alloy`. |
| OpenBao / Secrets | `Codestra-OpenBao` | Store Beyvra runtime secrets using `openbao/beyvra-secret-map.md`. |

## Beyvra Backend Signals Already Available

- `/health` platform health entrypoint.
- `/ready` platform readiness entrypoint.
- `/health/live` and `/health/ready` foundation health entrypoints.
- `/metrics` from `django_prometheus.urls`.
- Prometheus exporter thread on port `7001` in non-debug deployments.
- Structured JSON logs through `fx_utils.json_logging.JsonFormatter`.
- Bounded-cardinality custom metrics under the `beyvra_*` namespace.

Run Django without the auto-reloader in production-like local checks when the Prometheus exporter
thread is active:

```bash
python manage.py runserver 127.0.0.1:8000 --noreload
```

## Production Wiring Order

1. Put all Beyvra secrets in OpenBao and inject them into the runtime environment or Docker secrets.
2. Start Postgres, Redis, backend, frontend/BFF, worker processes, and realtime infrastructure.
3. Start exporters: node exporter, cAdvisor, Redis exporter, PostgreSQL exporter, and blackbox exporter.
4. Start Loki, Tempo, Prometheus, Alertmanager, and Grafana.
5. Start Alloy or the OpenTelemetry collector for logs, traces, and scrape forwarding.
6. Import the Beyvra Prometheus scrape config and alert rules.
7. Provision Grafana datasources and dashboards.
8. Verify `/health`, `/ready`, `/metrics`, password reset email evidence, public intake, realtime health, and trading provider governance.

## Readiness Evidence Required Before Production

- Backend `/ready` returns ready from the production network path.
- Prometheus has live `up{service="beyvra-backend"}` and `beyvra_*` series.
- Blackbox probes for public site, sign-in, sitemap, legal pages, and API health are green.
- Loki receives JSON logs with `service=beyvra-backend`.
- Alertmanager receives a controlled test alert and routes it to the expected receiver.
- OpenBao audit logging is enabled and application secret access uses least-privilege policies.
- Password reset and registration email evidence is attached to readiness, not only documented.
