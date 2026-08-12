# Migration Convergence Plan

## Starting migration graph

The frozen `canonical_trading` app started at `0001_initial`. Independently developed stacks created two `0002` migrations:

- `0002_simulated_trading`, followed by reconciliation and execution-control migrations through `0008_executionqualityreport_revision_and_more`;
- `0002_tradingorder_eligibility_evaluated_at_and_more`, which adds eligibility/idempotency simulation state using idempotent PostgreSQL DDL and `SeparateDatabaseAndState`.

## Conflicting leaves

```text
canonical_trading.0002_tradingorder_eligibility_evaluated_at_and_more
canonical_trading.0008_executionqualityreport_revision_and_more
```

## Combined desired schema

The combined state retains one writable `TradingOrder`, simulation account/reservation/trade projections, risk evidence, reconciliation evidence, and execution routing/quality/governance evidence. The legacy `trade.Trade` surface is compatibility data and is not the canonical order/trade write authority. Post-trade and valuation models remain separate workflow/evidence/read-model domains.

## Merge strategy

`0009_merge_converged_trading_graph` depends on both leaves. It contains no database operation because the branches create disjoint state. This is an intentional graph merge after reviewing the desired model state; neither migration is renumbered. Any drift discovered by `makemigrations --check --dry-run` must be expressed as a subsequent schema migration rather than hidden in this merge.

Provider governance also had two disjoint leaves: the provider policy/NewsData chain and the disabled Polygon OMS registration. `0005_merge_provider_governance_graph` joins those leaves without operations because both retain fail-closed provider registrations.

## Data migration requirements

No cross-branch data rewrite is required for the merge itself. Eligibility fields have fail-closed defaults and simulation-only markers. Existing rows must remain simulation-classified until an explicit reviewed backfill exists. No migration may create or infer Financial Service ledger, balance, reservation, or settlement records.

## Rollback strategy

Rollback the reversible execution-control tranche to `canonical_trading.0003_reconciliation_evidence`, then reapply through `0009`. The eligibility migration has explicit reverse SQL and may be rolled back separately only in an isolated certification database. Append-only trigger migrations must use their checked-in reverse SQL. Never run rollback certification against production.

## Certification matrix

```text
empty PostgreSQL 16 database -> latest
existing consolidation schema -> latest
latest -> appropriate reversible tranche
reapply -> latest
makemigrations --check --dry-run -> no drift
showmigrations/graph leaf count -> one canonical_trading leaf
```

## Exact-candidate result (2026-08-12)

- PostgreSQL server: 16 (disposable database `beyvra_convergence_cert_20260812`).
- Current roots: 34 application/framework roots reported by `MigrationLoader`.
- Current `canonical_trading` leaf: `0009_merge_converged_trading_graph`.
- Conflicts reported by `MigrationLoader.detect_conflicts()`: `{}`.
- Empty database to latest: PASS.
- Reversible tranche (`valuation` latest to zero): PASS.
- Reapply to latest: PASS.
- `makemigrations --check --dry-run`: `No changes detected`.
