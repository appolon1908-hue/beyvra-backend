# Institutional account certification evidence

Candidate branch: `feat/institutional-account-clearing-authority`

This package contains synthetic, non-production evidence only. No customer PII,
provider credentials, broker identifiers, custody identifiers, or Financial
Service database access are included.

- PostgreSQL 16 migration-from-zero, rollback, and reapply: PASS
- Django migration drift: NONE
- Synthetic load: 100 institutions and 10,000 subaccounts
- Restore into disposable PostgreSQL 16: PASS
- Reconciliation and audit continuity after restore: PASS
- Current-source secret scan: 0 findings
- Dependency and container critical vulnerabilities: 0
- SBOM: `sbom.cdx.json` (CycloneDX)

Live execution, custody, clearing, settlement, real wallet, and money movement
remain disabled. The application has no Financial PostgreSQL connection.
