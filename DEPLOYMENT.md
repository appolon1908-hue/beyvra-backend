# Production deployment runbook

This repository is prepared for an Ubuntu host running Docker Compose behind a
TLS reverse proxy. Production changes remain manual and protected by the GitHub
`production` environment.

## Release gates

Before approving a deployment, require a green pull request, reviewed database
migrations, a successful staging smoke test, verified payment-sandbox flows,
and a recent restore test. Rotate all credentials previously committed or sent
through chat before creating the production `.env` file.

## Host preparation

1. Install Docker Engine and the Compose plugin from Docker's Ubuntu repository.
2. Create an unprivileged deployment user with access only to Docker and
   `/srv/backend`; disable password and root SSH after key access is verified.
3. Create `/srv/backend/.env` from `.env.example` using random secrets and a
   secrets manager. Set explicit HTTPS origins and hosts; never enable global
   CORS in production.
4. Keep PostgreSQL, Redis, Flower, and StatsD off the public network. Publish
   only the reverse-proxy entry point.
5. Configure encrypted off-host backups, retention, alerting, and a restore
   drill before accepting real money.

The database image moves from PostgreSQL 12 to 16. Existing production data
must be migrated through a tested `pg_dump`/`pg_restore` staging rehearsal;
never point the new image directly at an old PostgreSQL 12 data directory.

## GitHub environment

Configure these `production` environment secrets:

- `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`
- `GHCR_USER`, `GHCR_PULL_TOKEN`

Require manual approval on the environment. Run **Build and deploy backend**
with `deploy=false` to publish an image only. Set `deploy=true` only after all
release gates pass. The deploy job creates a compressed PostgreSQL backup before
changing containers and deploys the commit-addressed image tag.

## Verification

After staging or production deployment, verify:

```bash
docker compose -f docker-compose.yaml ps
curl --fail http://127.0.0.1:${PORT}/healthz
docker compose -f docker-compose.yaml exec -T web python manage.py check --deploy
```

Then exercise authentication, wallet ownership boundaries, a sandbox deposit,
a sandbox withdrawal failure/refund, trade creation, WebSockets, Celery, and
metrics/alerts. Reconcile wallet balances against transaction records.

## Rollback

Redeploy the previous commit-addressed `BACKEND_IMAGE` and run `docker compose
up -d --wait`. Application rollback must not reverse an already-applied database
migration blindly. Use a reviewed backward migration or restore into a separate
database, validate it, and then cut over. Preserve the failed release logs,
image digest, database backup, and payment-provider event IDs for investigation.
