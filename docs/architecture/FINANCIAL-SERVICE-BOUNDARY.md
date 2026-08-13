# Financial Service Boundary

Financial Service is the only authority for real cash balances, ledger postings, real reservations/releases, monetary settlement, and settlement finality. The application database contains no Financial Service database alias or credentials and performs no direct Financial Service SQL.

## Mutation classification

| Area | Classification | Permitted mutation |
|---|---|---|
| `FX/wallet` | LEGACY + SIMULATION | demo wallet only; legacy real-value handlers fail closed |
| `FX/payments` | LEGACY | compatibility/provider webhook evidence; real movement disabled |
| `FX/trade/demo_engine.py` | SIMULATION | demo orders, demo wallet projection, and demo events only |
| `FX/real_wallet` | FROZEN LEGACY SCHEMA | not installed, routed, imported, or worker-discovered; retained only so historical source/migrations document preserved tables |
| `FX/financial_boundary` | READ_MODEL + REAL_FINANCIAL CLIENT BOUNDARY | mTLS service calls, intent/idempotency/evidence, and projections; no local real ledger/balance mutation |
| `FX/financial_client` | REAL_FINANCIAL CLIENT BOUNDARY | typed fail-closed transport to Financial Service only |
| `FX/apps/trading` | SIMULATION | `SimulatedAccount`, `SimulatedReservation`, `SimulatedTrade`, and position projections |
| `FX/apps/post_trade` | READ_MODEL + WORKFLOW | provider-neutral allocation, settlement intent, and status projection |
| `FX/treasury` | SIMULATION + READ_MODEL | planning/read models only; real transfers compile-time disabled |

## Settlement split

```text
BACKEND_OWNS=trade capture; allocation; post-trade workflow; settlement intent/projection; settlement status projection
FINANCIAL_SERVICE_OWNS=cash authority; ledger postings; real reservations; real releases; monetary settlement; settlement finality
```

`post_trade.SettlementInstruction` is workflow intent. It cannot attest to monetary finality and cannot post cash or ledger entries.

The former `real_wallet` application is deliberately absent from
`INSTALLED_APPS`, root URLs, ASGI routing, and runtime imports. Its historical
migrations are not deleted and no destructive migration drops its tables; an
existing deployment can preserve those records while Financial Service owners
coordinate any later archival or controlled data migration.

## Enforced safety

Application settings hard-disable real money, real trading, external execution, real deposits/withdrawals/transfers, real settlement, live clearing/custody, live broker routing, and FIX live sessions. A Django security system check rejects any Financial Service database environment variables or additional database aliases.
