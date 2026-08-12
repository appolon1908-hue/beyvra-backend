# Financial Boundary Audit

The exact candidate was scanned for balance, wallet, ledger, deposit,
withdrawal, reservation, release, settlement, cash, Financial Service database
credentials, PostgreSQL clients, and raw SQL.

| Path | Classification | Resolution |
|---|---|---|
| `FX/wallet` | SIMULATION_ONLY + DEPRECATED_NONAUTHORITATIVE | real rows hidden; all legacy mutation endpoints fail closed; canonical demo flow is separate |
| `FX/payments` | LEGACY | no authoritative real movement; compatibility endpoints are deprecated |
| `FX/trade/demo_engine.py` | SIMULATION_ONLY | demo balance and trade projections only |
| `FX/apps/trading` | SIMULATION_ONLY | explicit `SimulatedAccount`, `SimulatedReservation`, `SimulatedTrade`, and `SimulatedPosition` |
| `FX/apps/post_trade` | READ_MODEL + PROVIDER_NEUTRAL_WORKFLOW | allocation and settlement intent/status only |
| `FX/treasury` | SIMULATION_ONLY + READ_MODEL | no real transfer authority |
| `FX/financial_boundary` | FINANCIAL_SERVICE_CLIENT_BOUNDARY | canonical fail-closed `/api/v1/` contract; no database access |
| `FX/financial_client` | FINANCIAL_SERVICE_CLIENT | typed transport contract; mutations disabled in this candidate |
| `FX/real_wallet` | FROZEN_LEGACY | removed from installed apps, URLs, ASGI, workers, and runtime imports; historical migrations/tables preserved without mutation |

The only raw SQL found under the frozen legacy tree is its historical immutable
ledger migration. Because the app is not installed, that SQL is not part of the
candidate migration graph and is not application-to-Financial-Service SQL.

```text
AMBIGUOUS_REAL_BALANCE_MUTATION_PATHS=0
AMBIGUOUS_REAL_SETTLEMENT_PATHS=0
APPLICATION_DIRECT_FINANCIAL_DB_ACCESS=DENIED
APPLICATION_DIRECT_FINANCIAL_SQL=0
APPLICATION_SHADOW_REAL_LEDGER=NO
FINANCIAL_SERVICE_CHANGED=NO
```
