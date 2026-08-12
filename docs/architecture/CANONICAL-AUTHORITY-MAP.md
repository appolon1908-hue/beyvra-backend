# Beyvra canonical authority map

This map records the target authority boundary. `CONFLICT` means the checked-out and active mission branches do not yet enforce the target as one integrated system.

| State | Canonical authority | Canonical model/service | API/event | Read models / legacy | Status |
|---|---|---|---|---|---|
| Identity/authentication | Backend identity service | `users.User`, integration external identity, auth services | `/api/v1/auth/*`, session events | legacy `/api/user/*` | CONFLICT |
| Tenant | Backend organization authority | `integrations.Organization/Membership` | tenant context | user/wallet tenant copies | CONFLICT |
| Account/institution/subaccount | Backend institutional authority; Financial Service owns monetary mapping | institutional mission models/services | institutional V1 APIs/events | legacy wallet/user account fields | UNMERGED |
| Instrument/symbol/venue | Backend reference-data authority | reference-data mission | instrument APIs and market identity events | three `Asset` models, raw symbols | CONFLICT |
| Market data/quote/tick/candle/status | Backend governed market-data authority | market authority/provider governance | market V1 APIs, `market.*` | Alpaca/CoinGecko/direct chart routes | CONFLICT |
| News | Backend governed news authority | news service | news V1 APIs, `news.*` | Alpaca news compatibility | CONFLICT |
| Order/preview/reservation | Backend trading authority for simulation; real order disabled | `apps.trading` | trading V1 APIs, order events | legacy `trade.Trade`, Alpaca order API | CONFLICT |
| Routing/execution/fill | Backend execution authority; external provider is evidence | execution mission | execution APIs/events | provider-native state | UNMERGED |
| Trade/allocation/post-trade | Backend post-trade authority | post-trade mission | post-trade APIs/events | legacy trade/reporting models | UNMERGED |
| Monetary settlement/balance/hold/release | Financial Service only | Financial PostgreSQL ledger | private mTLS financial API, financial events | backend real-wallet ledger | CONFLICT |
| Position | Backend position projection from canonical fills | valuation/post-trade mission | position API/events | portfolio and trade-derived views | CONFLICT |
| Buying power/margin/collateral/exposure | Backend simulation risk authority; Financial Service supplies real balance facts | risk mission | risk APIs/events | frontend/legacy calculations | UNMERGED |
| Fee/commission/entitlement | Backend pricing/entitlement authority | pricing mission | fee/entitlement APIs/events | legacy constants/provider values | UNMERGED |
| Treasury/liquidity/funding | Backend treasury planning; Financial Service executes authorized money effects | treasury mission | treasury APIs/events | none canonical in checkout | UNMERGED |
| Valuation/cost basis/tax lot/P&L/NAV/performance | Backend valuation authority | valuation mission | valuation APIs/events | portfolio/reporting/frontend calculations | CONFLICT |
| Compliance/regulatory records | Backend compliance/regulatory authority | compliance mission | compliance APIs/events | legacy KYC/admin mutation | CONFLICT |
| Audit/evidence/statement | Owning domain writes immutable evidence; backend reporting composes | domain audit plus statement mission | operator/report APIs | multiple writable audit tables | AMBIGUOUS |
| Feature flags/kill switches | Owning service control authority with global fail-closed hierarchy | backend trading control and Financial Service governance | operator controls/audit events | environment and DB-local booleans | CONFLICT |
| Health/degraded mode | Each service readiness authority; SRE aggregates | health checks/SRE mission | `/health/live`, `/health/ready` | legacy `SystemHealth` | CONFLICT |
| Webhook | Receiving domain owns inbox and deduplication | notification/provider/Financial inbox | signed webhook endpoints/events | multiple delivery tables | STRUCTURAL DUPLICATE |
| Developer API key/OAuth scope | Backend developer platform authority | service-token/platform API mission | developer APIs/audit events | legacy admin RBAC | UNMERGED |

Financial Service is separate from the application dependency chain and is never imported as an application database. Provider systems never replace platform authority.

