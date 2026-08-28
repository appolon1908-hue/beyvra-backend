# Backend deployment

## Required configuration

Copy `.env.example` to the deployment secret store and provide real values. At minimum configure Django's `SECRET_KEY`, PostgreSQL, Redis, email, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`, payment-provider secrets, `POLYGON_API_KEY`, `NEWS_DATA_API_KEY`, and `FIXER_API_KEY`.

Never commit the populated environment file. Rotate the API credentials that were previously present in repository history.

## Validate

```sh
docker build -t beyvra-backend:release -f FX/Dockerfile .
docker compose config
docker compose up -d --build
docker compose ps
curl --fail https://YOUR_HOST/metrics
```

The production web entrypoint waits for PostgreSQL and Redis, applies migrations, collects static files, and starts Gunicorn. Celery worker and beat services must use the same image and environment.

For a self-contained local stack, copy `.env.docker.example` to `.env` and run:

```sh
docker compose -f docker-compose.local.yaml up -d --build
docker compose -f docker-compose.local.yaml ps
```

The local compose file includes PostgreSQL 16, Redis, NATS without TLS, Centrifugo, Gunicorn, Daphne, Celery, and realtime publisher workers. It is intentionally separate from production because the production stack expects external monitoring/financial networks and TLS assets for NATS/Centrifugo.

Before directing traffic to a new release, back up PostgreSQL and run migrations as a distinct deployment step if your platform can execute more than one web replica concurrently.

The `db-backup` service writes a PostgreSQL custom-format dump immediately on
startup and then every `BACKUP_INTERVAL_SECONDS` (daily by default), retaining
`BACKUP_RETENTION_DAYS` days locally. Verify a new file exists in `backups/`
after every deployment and copy it to encrypted off-host storage. A guarded
restore helper is available at `scripts/restore-backup.sh`; always restore into
a separate staging database first.

## Host and network preparation

1. Install Docker Engine and the Compose plugin from Docker's Ubuntu repository.
2. Use an unprivileged deployment account with key-only SSH and access limited to `/srv/backend` and Docker.
3. Keep PostgreSQL, Redis, Flower, and StatsD off the public network. Publish only the TLS reverse proxy.
4. Configure encrypted off-host backups, retention alerts, and a successful restore drill before accepting real money.

The release moves PostgreSQL from 12 to 16. Existing data must be migrated through a tested `pg_dump`/`pg_restore` rehearsal. Never attach the PostgreSQL 12 data directory directly to PostgreSQL 16.

## Protected GitHub deployment

Configure a GitHub `production` environment with required approval and these secrets:

- `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`
- `GHCR_USER`, `GHCR_PULL_TOKEN`

Run **Build and deploy backend** with `deploy=false` to publish an immutable image only. Use `deploy=true` after staging approval. The workflow backs up PostgreSQL before deploying the commit-addressed image.

After deployment, verify authentication, wallet ownership boundaries, MFA, a sandbox deposit and failed withdrawal/refund, trade creation, WebSockets, Celery, health checks, and monitoring. Reconcile wallet balances against transactions.

## Rollback

Redeploy the previous commit-addressed `BACKEND_IMAGE` and run `docker compose up -d --wait`. Do not blindly reverse an applied schema migration. Use a reviewed backward migration or restore the pre-deploy backup into a separate database, validate it, and then cut over. Preserve payment-provider event IDs, logs, the failed image digest, and the database backup for investigation.
