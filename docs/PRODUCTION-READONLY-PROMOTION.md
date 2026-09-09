# Beyvra backend read-only promotion runbook

## Protected environments

Create two GitHub environments:

- `staging-readonly`
- `production-readonly`

Both environments should require approval and restrict deployment branches to
`main`.

### Required environment secrets

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_KNOWN_HOSTS`
- `GHCR_USER`
- `GHCR_TOKEN`

The deploy identity must be limited to the Beyvra deployment directory and the
minimum Docker operations required by the reviewed deployment script.

### Required environment variables

- `DEPLOY_PATH`
- `PUBLIC_SERVER_NAME`
- `FINANCIAL_API_NETWORK`
- `MONITORING_NETWORK`
- `BACKUP_OFFHOST_PATH`
- `PYTHON_BASE_IMAGE` — immutable `repository@sha256` value
- `NGINX_BASE_IMAGE` — immutable `repository@sha256` value
- `POSTGRES_IMAGE` — immutable `repository@sha256` value
- `REDIS_IMAGE` — immutable `repository@sha256` value
- `NATS_IMAGE` — immutable `repository@sha256` value
- `CENTRIFUGO_IMAGE` — immutable `repository@sha256` value
- `STATSD_EXPORTER_IMAGE` — immutable `repository@sha256` value

The server must already contain the runtime `.env`, protected secret
directories, realtime TLS material, media directory, and a writable off-host
backup mount. None of these secrets are copied from GitHub source control.

## Stage the candidate

Run **Publish and deploy immutable Beyvra backend** from `main` with:

- `source_sha`: the full current protected-main SHA;
- `target`: `staging-readonly`;
- `publish_images`: `true`;
- `deploy`: `true`;
- a unique `change_id`;
- `allow_schema_migrations`: `false`;
- `migration_compatibility_approved`: `false`.

The workflow refuses to build from an older or non-main source. Save the
release manifest, deployment evidence, exact backend digest, and exact edge
digest.

## Rehearse rollback

Cause a controlled verification failure in a non-production rehearsal or use a
candidate known to fail a harmless identity check. Confirm that the deploy
script restores:

- backend image;
- edge image;
- PostgreSQL image;
- Redis image;
- NATS image;
- Centrifugo image;
- StatsD exporter image;
- static snapshot;
- previous source identity.

Record recovery time, data-integrity checks, health/readiness, and version
readback. Do not proceed if the previous release is not a complete immutable
tuple.

## Promote the exact candidate

Run the same workflow from `main` with:

- the same `source_sha`;
- `target`: `production-readonly`;
- `publish_images`: `false`;
- `backend_image`: the staging-certified backend digest;
- `edge_image`: the staging-certified edge digest;
- `deploy`: `true`;
- a new production `change_id`;
- schema migration inputs still `false`.

The workflow rejects a production rebuild. Stop and roll back on identity
mismatch, readiness failure, backup failure, monitoring loss, database drift,
write acceptance, or any live-effect counter movement.

## Active-mode boundary

This runbook does not authorize active trading, real money, external broker
execution, payments, deposits, withdrawals, transactional email, or background
execution workers. Those capabilities require a separate reviewed release,
financial command/idempotency certification, provider credentials, and an
explicit activation decision.
