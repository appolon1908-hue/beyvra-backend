# Treasury Liquidity Certification Evidence

Mission: simulation-only treasury and liquidity control plane.

## Candidate and rollback

- Starting SHA: `d9fd2faabb5cccfa929c3e2acac8fedb61975ad2`
- Branch: `feat/treasury-liquidity-authority`
- Backup: `/root/backups/beyvra-treasury-liquidity-20260811T222946Z`
- Bundle verification and SHA256 manifest: PASS

## Boundaries

- Real balance authority: Financial Service (future read contract)
- Application shadow real ledger: none
- Application Financial PostgreSQL access: none
- Provider reads/transfers: none
- Live treasury execution URL: absent and resolver-tested
- All treasury data carries simulation semantics; `LIVE` is not an allowed environment.

## Local certification

- PostgreSQL: 16
- Migration from zero: PASS
- Rollback: PASS
- Reapply: PASS
- Drift: none
- Django system check: PASS
- Treasury tests: 18 PASS; includes segregation, stale collateral, tenant isolation, idempotency conflict, true intraday peak, reconciliation, API/RBAC/realtime, and no-live-route tests.
- OpenAPI file: `contracts/openapi/beyvra-treasury-v1.yaml`
- OpenAPI/runtime route inventory: 37/37; drf-spectacular validation PASS; drift none.
- Reconciliation checks: 14
- 10,000-position isolated load: aggregate p50 2.495 ms, p95 2.779 ms, p99 4.265 ms; reconciliation 219.573 ms; no false positives.
- Restore fixture: 1 account, 1 reconciliation run, 2 immutable audit events survived PostgreSQL dump/restore.
- Current-source gitleaks: PASS. Trivy dependency/config: 0 critical. Candidate container: 0 critical. CycloneDX SBOM generated.

The full legacy repository suite discovered 322 tests. A correctly configured rerun passed its dependency setup and progressed through the suite, but the host filesystem reached 100% and the disposable PostgreSQL instance returned `DiskFull` during legacy tests. No treasury test failed; the complete repository result is therefore infrastructure-blocked rather than certified PASS.

## Safety assertions

`REAL_TREASURY_TRANSFERS_ENABLED`, `REAL_CASH_MANAGEMENT_ENABLED`, `REAL_COLLATERAL_MOVEMENT_ENABLED`, `REAL_INTRADAY_FUNDING_ENABLED`, `REAL_CREDIT_ENABLED`, and `REAL_SETTLEMENT_ENABLED` are hard false. No production or Financial Service repository was changed.

## External boundary

Approved isolated staging, finance/risk production buffer policy, legal segregation interpretation, and any real Financial Service balance/transfer contract remain externally owned and were not self-certified.
