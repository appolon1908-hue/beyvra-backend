# Valuation/P&L certification evidence

- Candidate base: `97b4cbb2bff83d6860050e450648b6f06f536f54`
- Environment: Python 3.11 container and PostgreSQL 16
- Migration from zero: PASS
- Migration drift: NONE
- Django system check: PASS
- Focused valuation tests: 7 PASS
- Post-trade regression tests: 13 PASS
- Full backend suite: 310 PASS
- Migration rollback/reapply: PASS
- OpenAPI validation: PASS (`4dac00d1cb24d0cc331b3ae524072fa0e65c3f04d539b7745a54fe319b9ddb1d`)
- Source secret scan: PASS (0 findings)
- Dependency/config/container critical scan: PASS (0 critical findings)
- CycloneDX SBOM: generated as `sbom.cdx.json`
- Explicit fixture prices/FX only: PASS
- Binary-float rejection test: PASS
- Direct Financial DB access: none introduced
- Real execution, settlement, money, tax reporting, and NAV publication: disabled

The API intentionally returns `FEATURE_DISABLED` for operator reconciliation, FX publication, performance publication, position recomputation, and tax-lot selection mutation until their complete governance/API workflows are implemented. Models and pure authorities exist, but these surfaces are not falsely certified.

Backup: `/root/backups/beyvra-valuation-pnl-20260811T225113Z/` (host-only evidence; not committed).
