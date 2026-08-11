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

## Versioning and immutability

Approvals carry a per-provider/environment version, creator principal,
canonical payload hash, and optional `supersedes_approval` link. PostgreSQL
triggers reject update or deletion of approved rows, provider-type mismatch,
invalid licenses, branching replacements, and non-sequential replacement
versions. Changes are represented by a new row that supersedes the current
approved leaf.

`credential_policy=REQUIRED` requires an explicitly versioned reference below
the protected root. Resolution rejects symlinks, unexpected owners, writable
parent directories, group/world-readable files, unexpected POSIX ACLs, and
unreadable files. `credential_policy=NONE` requires a null reference and is
the correct policy for an independently approved no-authentication provider.

Audit rows include the exact approval version, license, requested scope,
reference identifier/hash, request and correlation identifiers, caller, and
resolution time. A database trigger makes the audit table append-only.

The governed outbound inventory covers market history, CoinMarketCap legacy
views, NewsData, Alpaca news, and Alpaca economic-calendar access. No adapter
may reach its network client before governance resolution succeeds.

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
