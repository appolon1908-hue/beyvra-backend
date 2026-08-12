# Canonical Authority Map

This map is a hard integration boundary. A writable state has exactly one canonical owner. Adapters, projections, evidence records, and compatibility APIs may not mutate another owner's truth.

| State | Canonical owner | Permitted non-owner representation |
|---|---|---|
| ORDER | APPLICATION_BACKEND | provider mapping/evidence |
| EXECUTION | APPLICATION_BACKEND | provider execution evidence |
| TRADE | APPLICATION_BACKEND | reporting/read models |
| POSITION | APPLICATION_BACKEND_PROJECTION | cached frontend presentation only |
| MARKET_DATA | MARKET_DATA_AUTHORITY | application cache/read model |
| CASH_BALANCE | FINANCIAL_SERVICE | explicitly simulated balance or read-only projection |
| FINANCIAL_LEDGER | FINANCIAL_SERVICE | immutable reference/evidence only |
| RESERVATION | FINANCIAL_SERVICE_FOR_REAL_VALUE | explicitly simulated reservation |
| MONETARY_SETTLEMENT | FINANCIAL_SERVICE | backend settlement intent/status projection |
| POST_TRADE_WORKFLOW | APPLICATION_BACKEND | Financial Service monetary references |
| VALUATION | APPLICATION_BACKEND_READ_MODEL | frontend formatting only |
| TREASURY | APPLICATION_BACKEND_SIMULATION_READ_MODEL | no real treasury transfer authority |
| REGULATORY_RECORD | APPLICATION_BACKEND_EVIDENCE_AUTHORITY | external filing adapter evidence |

## Binding rules

```text
AMBIGUOUS_CANONICAL_AUTHORITIES=0
REAL_FINANCIAL_BALANCE_MUTATION_IN_BACKEND=PROHIBITED
REAL_LEDGER_MUTATION_IN_BACKEND=PROHIBITED
APPLICATION_DIRECT_FINANCIAL_DB_ACCESS=DENIED
APPLICATION_DIRECT_FINANCIAL_SQL=0
APPLICATION_SHADOW_REAL_LEDGER=NO
```

Backend settlement records mean provider-neutral workflow intent or status projection. They never establish monetary settlement or finality. OMS/provider-native objects remain adapters, mappings, and evidence; provider identifiers are references only.

All real-value features fail closed. The integrated candidate does not authorize real trading, external execution, live provider routing, real settlement, deposits, withdrawals, or treasury transfers.
