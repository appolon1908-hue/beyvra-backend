# Canonical Authority Map

This map is a hard integration boundary. A writable state has exactly one canonical owner. Adapters, projections, evidence records, and compatibility APIs may not mutate another owner's truth.

| State | Owner | Canonical model/service | Canonical API/event | Read models and legacy disposition |
|---|---|---|---|---|
| Identity | APPLICATION_BACKEND | `users.User` / users services | `/api/v1/me/`; security events | provider identities are mappings |
| Authentication | APPLICATION_BACKEND | users authentication services | `/api/v1/auth/*` | `/api/user/*` deprecated compatibility |
| Tenant | APPLICATION_BACKEND | organization/tenant resolution | tenant-scoped V1 APIs | provider tenants are mappings |
| Account | APPLICATION_BACKEND | user and demo-account records | `/api/v1/me/` | Financial accounts are external references |
| Institution | APPLICATION_BACKEND | `institutional.Institution` | `/api/v1/institutional/*` | none authoritative elsewhere |
| Subaccount | APPLICATION_BACKEND | institutional subaccount | institutional V1 API | provider accounts are mappings |
| Instrument, Symbol, Venue | MARKET_DATA_AUTHORITY | reference-data registry | `/api/v1/instruments/*`; `market.*` | provider symbols normalized to references |
| Market Data, Quote, Trade Tick, Candle, Market Status | MARKET_DATA_AUTHORITY | pricing/market-data services | `/api/v1/market/*`; `market.*` | caches are read models only |
| News | NEWS_AUTHORITY | normalized news service | `/api/v1/news*`; `news.*` | provider payload retained as evidence |
| Order and Order Preview | APPLICATION_BACKEND | `apps.trading.TradingOrder`; simulation application service | `/api/v1/trading/orders*`; `trading.order.*` | legacy trade endpoints compatibility-only |
| Order Reservation | FINANCIAL_SERVICE_FOR_REAL_VALUE | Financial Service; `SimulatedReservation` for simulation | Financial boundary; trading events | no ambiguous backend real reservation |
| Execution and Routing Decision | APPLICATION_BACKEND | canonical execution/routing records and services | `/api/v1/execution/*`; `trading.execution.*` | provider executions are evidence/mappings |
| Fill | APPLICATION_BACKEND | canonical simulated fill identity | execution API; `trading.execution.*` | provider fill IDs are references |
| Trade and Trade Allocation | APPLICATION_BACKEND | canonical post-trade capture/allocation | `/api/v1/post-trade/*`; `trading.trade.*`, `post_trade.*` | reporting models are projections |
| Position | APPLICATION_BACKEND_PROJECTION | executed-trade position projection | trading/valuation V1 APIs | legacy portfolio/frontend state is read-only |
| Post-Trade Workflow | APPLICATION_BACKEND | `apps.post_trade` services | `/api/v1/post-trade/*`; `post_trade.*` | none |
| Settlement Instruction | APPLICATION_BACKEND_PROVIDER_NEUTRAL_INTENT | post-trade instruction/projection | post-trade API/event | cannot establish monetary finality |
| Monetary Settlement | FINANCIAL_SERVICE | Financial Service settlement authority | Financial Service contract | backend status is projection only |
| Cash and Real Balance | FINANCIAL_SERVICE | Financial Service cash authority | fail-closed boundary adapter | demo wallet is explicit simulation/legacy |
| Financial Ledger | FINANCIAL_SERVICE | Financial Service immutable ledger | Financial Service contract | backend ledger-shaped records non-authoritative |
| Real Reservation and Release | FINANCIAL_SERVICE | Financial Service reservation services | Financial Service contract | simulation reservation explicitly separate |
| Fee and Commission | APPLICATION_BACKEND_CALCULATION | canonical trading/post-trade fee calculation | trade/post-trade API/events | real cash posting remains Financial Service |
| Entitlement and Subscription | APPLICATION_BACKEND | pricing/entitlement services | `/api/v1/*` entitlement APIs | provider capability data is evidence |
| Margin, Collateral, Buying Power, Exposure | APPLICATION_BACKEND_SIMULATION_RISK | risk authority services/read models | risk V1 APIs/events | no real credit or collateral movement |
| Valuation, Cost Basis, Tax Lot, Realized P&L, Unrealized P&L, NAV, Performance | APPLICATION_BACKEND_READ_MODEL | `apps.valuation` | valuation V1 APIs; `valuation.*` | frontend formats values only |
| Treasury, Liquidity, Funding Requirement | APPLICATION_BACKEND_SIMULATION_READ_MODEL | treasury simulation services | treasury V1 APIs; `treasury.*` | real transfers prohibited |
| Regulatory Record, Audit Record, Statement, Evidence Manifest | APPLICATION_BACKEND_EVIDENCE_AUTHORITY | regulatory/operations evidence services | regulatory/system events and APIs | external filings remain adapters |
| Feature Flag | APPLICATION_BACKEND_CONFIGURATION | fail-closed Django settings | operator read surfaces | aliases prohibited for high-risk flags |
| Kill Switch | APPLICATION_BACKEND_OPERATIONAL_CONTROL | operations hierarchy | operator APIs; `system.*` | child services cannot bypass parent halt |
| System Health and Operational Mode | APPLICATION_BACKEND_OPERATIONAL_CONTROL | platform health/degraded-mode services | health/readiness APIs; `system.*` | deployment probes consume only |
| Provider-Native Objects | MAPPING_CAPABILITY_OR_EVIDENCE_ONLY | provider adapters | provider/operator APIs | never canonical order/trade/balance/settlement |

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
