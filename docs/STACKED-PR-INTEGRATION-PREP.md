# Stacked PR integration preparation

## Frontend dependency map

Protected frontend main is `f4d8f77befdaf39193b4693e009024c826ae8405`.
The actual open ancestry is broader than PR6 → PR8 → PR9:

```text
main → PR2 agent/auth-flow (open)
main → PR3 realtime/frontend-manager (open draft)
main → PR4 feat/account-scoped-demo-events (open)
PR4 branch → PR5 feat/chart-phase5-news-calendar (open draft, dirty)
PR5 branch → PR6 feat/beyvra-canonical-api-realtime-prep (open draft)
PR6 branch → PR7 feature/beyvra-charts-ui-completion (open draft)
PR7 branch → PR8 agent/beyvra-frontend-ux-e2e-hardening (open draft)
PR8 branch → PR9 feat/simulated-e2e-trading-ui (open draft)
```

PR6 has exactly two commits relative to its declared PR5 base:

- `3ddf0ae552f18d309b7758426cce55958b0e88ee` canonical client/realtime work;
- `b257ca9e71368defedbd17158c70b027e4862c45` corrected the chart unavailable-error assertion.

The original PR6 CI failure expected the raw sentinel
`GENUINE_5S_SOURCE_UNAVAILABLE`; the implementation correctly returned the mapped
safe message. The second commit fixed that test. Current exact-head CI and local
typecheck, lint, 84 unit/realtime/chart tests, safe-error checks, brand checks,
production build, and production dependency audit pass.

Retargeting PR6 directly to main is unsafe today: it would expose 137 commits, 135
of which are prerequisite ancestry rather than PR6-owned commits. Normalize and
merge the prerequisite chain first, or create an explicitly reviewed consolidation
candidate. PR8 also depends on PR7, not directly on PR6. PR9 depends on PR8.

Exact PR8 and PR9 heads independently pass typecheck, lint, 89 tests, production
build, safe-error checks, and production dependency audit. Their current approvals
and CI become historical as soon as a base or head changes.

## Backend readiness

PR20 remains frozen at `ee474b09941ff86a2c281901852b1c4ba30a70ee`.
PR21 contains one unique commit, changes seven files, and creates no migration.
After PR20 merges, retarget PR21 to main and run Python 3.11/PostgreSQL 16 migration
from zero, drift detection, full tests, rollback/reapply, secret/dependency/container
scans, SBOM validation, and non-destructive staging API/realtime compatibility checks.

PR22 remains frozen at `b07a04fdde91b9c5eb6e3f12a80e212bd30aa305`.
It has five unique commits and one migration,
`apps/trading/migrations/0002_simulated_trading.py`. After PR21 merges, retarget
PR22 to main and repeat the full exact-head/base certification, including simulation,
100-request idempotency, rollback/reapply, safe errors, tenant isolation, realtime
gap recovery, and zero external/financial effects.

Chaos artifacts are prepared in disposable infrastructure. Fault injection remains
unauthorized until protected-main integration and full-stack staging certification.
