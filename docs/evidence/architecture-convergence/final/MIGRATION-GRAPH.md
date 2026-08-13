# Migration graph certification

PostgreSQL 16 applied the integrated graph from an empty database. The formerly incompatible `canonical_trading.0002` leaves converge at `0009_merge_converged_trading_graph`; the provider-governance leaves converge at `0005_merge_provider_governance_graph`.

```text
MIGRATION_GRAPH_CONFLICTS=0
MIGRATION_FROM_ZERO=PASS
MIGRATION_DRIFT=NONE
ROLLBACK=PASS (valuation 0002 and 0001 reversed)
REAPPLY=PASS (valuation 0001 and 0002 reapplied)
```
