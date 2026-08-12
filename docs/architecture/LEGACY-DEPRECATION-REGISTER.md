# Legacy and deprecation register

| Component | Type | Replacement | Current consumers | Removal prerequisites | Status |
|---|---|---|---|---|---|
| `/api/wallet/*` and `/api/payment/*` | API/model authority | demo trading APIs plus Financial Service client boundary | frontend legacy endpoint registry | migrate frontend, prove no real-wallet use, retain history | IN USE / CONFLICT |
| `/api/trades/*` | API/state model | canonical `/api/v1/trading/*` | frontend and tests | route/type migration and state-lineage tests | IN USE |
| direct Alpaca order endpoints | provider API | canonical execution adapter | unknown external consumers | consumer inventory and provider abstraction | UNKNOWN |
| `deposit` / `deposite` aliases | route | correctly spelled canonical route | compatibility clients unknown | telemetry and deprecation window | LEGACY |
| `market.compat.*` channels | realtime | generated V2 channel registry | frontend | update frontend and reconnect/gap tests | CONFLICT |
| backend `real_wallet` ledger | model/service | Financial Service API projection only | tests and dormant routes | data-retention decision and irreversible migration approval | QUARANTINE |
| duplicate asset/trade/audit/outbox families | model/service | domain authority map | migrations and legacy tests | integrated migration/data lineage plan | DO NOT DELETE |
