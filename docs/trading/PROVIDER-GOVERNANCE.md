# Authoritative provider governance

Provider activation is controlled by database records, not environment flags.
Resolution requires an enabled provider, a matching unexpired `APPROVED`
staging approval, a matching unexpired `APPROVED` license, allowed
product/symbol/region scope, and a resolvable protected credential file.

Failures return `PROVIDER_NOT_AVAILABLE`/HTTP 503 before any provider network
request. Decisions append an audit record containing only provider identity,
decision, reason code, and timestamp. Credential values are never loaded by
the governance resolver, returned by APIs, included in events, or written to
logs.

The deterministic test provider may be approved only inside isolated tests.
It proves the governance-to-JetStream publication contract and must never be
seeded into staging or production.

## Staging state

The governance tables are intentionally empty after migration. Market, news,
and calendar activation remain blocked until independently authorized records
and protected credential references are supplied.

## Rollback

Before migration, a PostgreSQL custom-format dump, Git bundle, and immutable
container image were saved under
`/root/backups/codestra-provider-governance-20260806T2030Z/` and tagged
`codestra-backend:rollback-pre-authoritative-governance-20260806T2030Z`.
Rollback requires stopping the staging web service, reverting the migration
with `manage.py migrate provider_governance zero`, redeploying the rollback
image, and verifying that all provider activation remains disabled. Restore
the database dump only if migration reversal fails; never restore it over a
running database.
