# Beyvra OpenBao Secret Map

OpenBao is the production authority for Beyvra runtime secrets. This file lists paths and consumers
only; it must never include secret values.

## KV Paths

| Path | Consumer | Required keys |
| --- | --- | --- |
| `kv/beyvra/production/django` | Backend API | `SECRET_KEY`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` |
| `kv/beyvra/production/database` | Backend API, workers | `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| `kv/beyvra/production/postgres-exporter` | PostgreSQL exporter | `POSTGRES_EXPORTER_URI`, `POSTGRES_EXPORTER_USER`, `POSTGRES_EXPORTER_PASSWORD` |
| `kv/beyvra/production/redis` | Backend API, workers, Redis exporter | `REDIS_URL`, `REDIS_PASSWORD` |
| `kv/beyvra/production/keycloak` | Backend identity BFF | `KEYCLOAK_BASE_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` |
| `kv/beyvra/production/email` | Backend identity/email readiness | `SMTP_HOST`, `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` |
| `kv/beyvra/production/google` | Frontend/BFF deployment | `GOOGLE_SITE_VERIFICATION`, `GOOGLE_TAG_ID`, `GOOGLE_ADS_ID` |
| `kv/beyvra/production/providers/market-data` | Provider gateway | `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `POLYGON_API_KEY`, `TWELVE_DATA_API_KEY`, `NEWS_DATA_API_KEY`, `COINGECKO_API_KEY` |
| `kv/beyvra/production/webhooks` | Backend API | `COMPLIANCE_WEBHOOK_SECRET`, `STRIPE_ENDPOINT_SECRET`, `STAGING_WEBHOOK_RECEIVER_SECRET` |
| `kv/beyvra/production/realtime` | Backend API, Centrifugo/NATS | `CENTRIFUGO_TOKEN_HMAC_SECRET`, `CENTRIFUGO_PROXY_SECRET`, `NATS_URL`, `NATS_CREDS` |
| `kv/beyvra/production/observability` | Alloy, Grafana, Prometheus, Alertmanager | `GRAFANA_ADMIN_PASSWORD`, `ALERTMANAGER_WEBHOOK_URL`, `OTEL_EXPORTER_OTLP_HEADERS` |

## Policy Requirements

- Backend API can read only its own Beyvra production paths.
- Exporters can read only the one credential path they need. PostgreSQL exporter credentials must come from the dedicated monitoring role, not the Beyvra app database owner.
- Grafana can read datasource credentials and admin bootstrap credentials only.
- Superset uses a read-only analytics database credential, never the application owner credential.
- CI can validate secret presence and freshness but cannot read secret values into logs.
- Audit logging must be enabled before application AppRole credentials are issued.

## Beyvra Mail Domain

Use `beyvra_mail_domain` as the deployment variable that selects the approved sender domain.
For Beyvra production it should resolve to `beyvra.com` unless a documented release changes the
sender authority.
