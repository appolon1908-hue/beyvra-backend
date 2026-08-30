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

## Endpoint And Credential Matrix

| System | Endpoint | Consumer | Exposure | Credential source | Production proof |
| --- | --- | --- | --- | --- | --- |
| Beyvra backend app metrics | `http://beyvra-backend:8000/metrics` | Prometheus, Alloy | Private observability network | None, private network only | `up{job="beyvra-backend-django"} == 1` and `beyvra_*` metrics present |
| Beyvra backend exporter | `http://beyvra-backend:7001/metrics` | Prometheus, Alloy | Private observability network | None, private network only | `up{job="beyvra-backend-exporter"} == 1` |
| Beyvra live health | `https://api.beyvra.com/health` | Blackbox exporter, release checks | Public HTTPS through edge/BFF | None | HTTP 200 probe success |
| Beyvra readiness | `https://api.beyvra.com/ready` | Blackbox exporter, release checks | Public HTTPS through edge/BFF | None | HTTP 200 only when dependencies are ready |
| Beyvra frontend | `https://beyvra.com/` | Blackbox exporter, Google systems | Public HTTPS | None | HTTP 200, valid TLS, indexable page |
| Beyvra sign-in | `https://beyvra.com/signIn?tab=login` | Blackbox exporter, auth smoke tests | Public HTTPS | Backend-owned HttpOnly cookies after login | Login smoke test reaches `/api/v1/session` |
| PostgreSQL exporter | `http://postgres-exporter:9187/metrics` | Prometheus | Private observability and database networks | `kv/beyvra/production/postgres-exporter` or `/run/secrets/postgres_exporter_*` | `pg_up == 1` |
| Redis exporter | `http://redis-exporter:9121/metrics` | Prometheus | Private observability network | `kv/beyvra/production/redis` if Redis auth is enabled | `up{job="beyvra-redis"} == 1` |
| Node exporter | `http://node-exporter:9100/metrics` | Prometheus | Private observability network | None, host-level deployment approval required | `up{job="beyvra-node"} == 1` |
| cAdvisor | `http://cadvisor:8080/metrics` | Prometheus | Private observability network | None, Docker socket access approval required | `up{job="beyvra-cadvisor"} == 1` |
| Blackbox exporter | `http://blackbox-exporter:9115/probe` | Prometheus | Private observability network | None | `probe_success == 1` for Beyvra public targets |
| Loki | `http://loki:3100/loki/api/v1/push` | Alloy | Private observability network | `kv/beyvra/production/observability` if tenant auth is enabled | JSON logs visible with `service=beyvra-backend` |
| Tempo | `tempo:4317` and `http://tempo:3200` | Alloy, Grafana | Private observability network | `kv/beyvra/production/observability` if auth is enabled | Trace search works for Beyvra services |
| Prometheus | `http://prometheus:9090` | Grafana, Alertmanager rule evaluation | Private observability network | `kv/beyvra/production/observability` if UI/API auth is enabled | Beyvra targets and alerts loaded |
| Grafana | Deployment-owned HTTPS hostname | Operators | Protected browser access | `kv/beyvra/production/observability` | Beyvra dashboards render Prometheus, Loki, and Tempo data |
| Alertmanager | Deployment-owned private API | Prometheus | Private observability network | `kv/beyvra/production/observability` | Controlled test alert reaches approved receiver |
| OpenBao | `https://bao.codestra.media` | Runtime secret injection, approved operators | Protected API/browser access only | AppRole/OIDC policy, never root token | Audit log shows least-privilege Beyvra reads |
| Superset | Deployment-owned HTTPS hostname | Analytics operators | Protected browser access | Dedicated read-only analytics database secret | Read-only Beyvra analytics dashboards load |

## PostgreSQL Exporter Contract

`Codestra-Postgres-Exporter` is the PostgreSQL metrics authority for Beyvra. Its private service
identity is `postgres-exporter:9187`, its metrics path is `/metrics`, and no public hostname or
published host port is allowed. Prometheus is the only routine scrape consumer.

The exporter must use a dedicated monitoring role. It must not use the Beyvra application database
owner, a superuser, a replication administrator, or any write-capable application identity.
Runtime credentials are supplied through OpenBao or approved runtime secret files:

- `/run/secrets/postgres_exporter_uri`
- `/run/secrets/postgres_exporter_user`
- `/run/secrets/postgres_exporter_password`

Production activation requires `pg_up == 1`, private-network scrape proof, least-privilege review,
cardinality review, immutable image evidence, and rollback evidence.

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
- PostgreSQL exporter reports `pg_up == 1` from `postgres-exporter:9187` on the private monitoring network.
- Password reset and registration email evidence is attached to readiness, not only documented.
