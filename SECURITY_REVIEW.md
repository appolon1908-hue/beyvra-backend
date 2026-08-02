# Backend security review

Review scope: authentication and authorization, wallet and withdrawal paths,
bank accounts, configuration, containers, and CI. This branch does not deploy
or alter production infrastructure, data, firewall rules, or DNS.

## Fixed on this branch

- Wallet transfers now require ownership of the source wallet, reject invalid
  amounts and self-transfers, and lock both wallet rows transactionally.
- Bank-account reads, changes, and deletes are scoped to the authenticated user.
- Withdrawal requests can no longer read or update another user's request or
  attach another user's bank account. Server-controlled workflow fields are
  read-only to clients.
- Administrative user/KYC/trade and platform-bank endpoints require an admin.
- The API defaults to authenticated access in every environment.
- CORS is deny-by-default and configured explicitly through environment values.
- A committed NewsData credential and reusable example secrets were removed.
  The exposed NewsData key must be revoked and replaced outside Git.
- Redis is internal-only; Flower and StatsD metrics bind to loopback.
- GitHub CI adds source, dependency, and container vulnerability scanning.

## Blocking issues before production deployment

1. Rotate every credential that has ever been committed or pasted into an
   external system. Store production values in a secrets manager, not `.env` in
   the repository or CI variables visible to untrusted jobs.
2. Redesign withdrawal processing as an idempotent ledger workflow. Balance
   reservation, gateway submission, success, failure, and refund must be atomic
   and auditable. The current implementation can leave pending rows and does
   not safely reserve funds against concurrent requests.
3. Add immutable double-entry ledger records for every balance mutation. Model
   helper methods currently update mutable balances directly.
4. Pin every dependency, remove the duplicate Celery Beat requirement, and
   resolve all `pip-audit` and container scan findings before release.
5. Upgrade PostgreSQL through a tested backup/restore migration. The current
   12.9 image is obsolete; do not replace it in-place against production data.
6. Add request timeouts, TLS-only endpoints, bounded retries, and circuit
   breakers to all payment, market-data, messaging, and geolocation calls.
7. Add integration tests with PostgreSQL/Redis plus adversarial authorization,
   concurrency, webhook replay, payment failure, and ledger-reconciliation
   cases. Existing coverage is incomplete and some tests reference old models.
8. Require protected branches, signed/reviewed releases, environment approval,
   least-privilege CI permissions, and an immutable image digest for deploys.

## Proposed deployment gates

CI must pass formatting/static analysis, Django checks and tests, secret scan,
dependency audit, image scan, and migration checks. A staging deployment should
then run smoke, authorization, payment-sandbox, restore, and rollback tests.
Production remains a manual approval using the exact staging-tested image digest.
