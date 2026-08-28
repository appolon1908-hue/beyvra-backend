# Duplication Register

| Concept | Canonical implementation | Adapted/superseded implementation | Status |
|---|---|---|---|
| Order | `canonical_trading.TradingOrder` | legacy `trade` endpoints | CONVERGED |
| Execution | canonical trading execution-control records | provider-native records as mappings/evidence | CONVERGED |
| Trade | `post_trade.Trade` captured from canonical simulated execution | `trade.Trade` compatibility history; `SimulatedTrade` execution projection | CONVERGED_BY_ROLE |
| Position | canonical `SimulatedPosition` executed-trade projection | post-trade effects and valuation are read/evidence models | CONVERGED_BY_ROLE |
| Portfolio summary | `apps.valuation.portfolio_api.PortfolioSummaryView` at `/api/v1/portfolio/summary` | `/api/portfolio/summary/` and `/api/v1/trading/portfolio` import the same canonical view and emit deprecation headers | CONVERGED |
| Real reservation | Financial Service | `SimulatedReservation` explicitly simulation-only | CONVERGED |
| Settlement | Financial Service monetary finality | `post_trade.SettlementInstruction` workflow intent/projection | CONVERGED_BY_ROLE |
| Outbox | `foundation.OutboxEvent` per application transaction pattern | news/demo outboxes adapted into the application outbox; disabled `PlatformOutboxEvent` app | CONVERGED |
| Platform operations | `operations` | `apps.platform_api` not installed/routed | CONVERGED |
| HTTP metrics | `apps.foundation.observability` | platform operations aliases canonical collectors | CONVERGED |
| Frontend sequence/gap recovery | `UnifiedRealtimeClient` | page controllers consume its transport; no second socket manager | CONVERGED |
