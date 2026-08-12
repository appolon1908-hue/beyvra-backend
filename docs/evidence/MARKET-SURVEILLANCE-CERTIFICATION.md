# Market Surveillance Certification Evidence

Candidate certification date: 2026-08-11 UTC.

## Scope and safety

- Candidate branch: `feat/market-surveillance-abuse-controls`
- Base: `origin/feat/instrument-reference-data-authority`
- Starting SHA: `cf4169e00d9355c8c70f5be157c34c8b8aa8d9f2`
- Financial Service was not modified.
- Production was not modified.
- Real trading, external execution, real money, wallet reads, deposits,
  withdrawals, and internal transfers remained disabled.

## Certification results

- PostgreSQL 16 migration from zero, rollback, and reapply: PASS
- Migration drift: NONE
- Django system check: PASS
- Focused surveillance tests: 7/7 PASS
- Surveillance plus trading tests: 47/47 PASS
- Full backend tests: 290/290 PASS (with disposable PostgreSQL 16 and Redis)
- Source secret scan: PASS (gitleaks)
- Dependency/configuration scan: PASS (Trivy; zero HIGH/CRITICAL findings)
- Candidate container scan: PASS (zero HIGH/CRITICAL findings)
- CycloneDX SBOM generation and validation: PASS
- Prometheus rule and Grafana JSON parsing: PASS
- Schema digest (SHA-256): `a7ca7251ee639df7712747bac476ec11e7a45828be247e64a7bd6bf294a61ff4`

## Pre-trade benchmark

The isolated PostgreSQL-backed fixture benchmark ran 1,000 evaluations:

| Control | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| Self-trade prevention | 0.437 ms | 0.611 ms | 0.808 ms |
| Full pre-trade surveillance | 1.883 ms | 2.680 ms | 4.251 ms |

These are engineering measurements from an isolated fixture environment, not
production SLO claims.

## External gates and limitations

- Candidate staging deployment and staging chaos/recovery execution were not
  authorized as part of protected-branch integration; status is
  `EXTERNAL_DEPLOYMENT_BLOCKED`.
- Beneficial-owner/linked-account STP is provider-neutral but cannot be
  certified until an authoritative linkage source exists.
- Surveillance retention duration requires an external compliance decision.
- Indicators are review signals only. They do not make legal conclusions or
  submit regulatory reports.
