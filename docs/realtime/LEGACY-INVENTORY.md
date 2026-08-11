# Realtime legacy inventory (staging)

Baseline: backend `c9e2628`, frontend `f1e3eb77`. Inventory is intentionally
conservative: components are not marked deletable until traffic and imports are
measured in staging.

| Component | Route/file | Classification | Replacement | Delete eligibility |
|---|---|---|---|---|
| Canonical gateway | `FX/ws/gateway.py`, `/ws/v1/` | ACTIVE_REQUIRED | `/ws/v2/` adapter after verification | NO |
| Platform chart feed | `src/pages/private/platform/hooks/useMarketFeed.ts` | ACTIVE_TO_MIGRATE | unified realtime client/Centrifugo | NO |
| Live market consumer | `FX/portfolio/consumers.py`, `/ws/market-data/` | LEGACY_COMPATIBILITY | gateway market channels | NO traffic proof |
| Portfolio sockets | `FX/portfolio/routing.py` | ACTIVE_TO_MIGRATE | account/portfolio channels | NO |
| Notification consumers | `FX/wsnotifications/consumers/*` | ACTIVE_TO_MIGRATE | notification channels | NO |
| Real-wallet stream | `FX/real_wallet/consumers.py`, `/ws/v1/real-wallet/` | ACTIVE_REQUIRED but feature-gated | wallet channels | NO |
| Legacy frontend sockets | `useSocketConnect`, `useCryptoSocketConnect`, `AssetSectionYA` | DUPLICATE/ACTIVE_TO_MIGRATE | shared client | NO |
| RealtimeSocketManager | `src/realtime/RealtimeSocketManager.ts` | ACTIVE_TO_MIGRATE | shared client | NO |
| Chart engine | `PlatformChartContainer`, Lightweight Charts | ACTIVE_REQUIRED | retain as primary | NO |
| Redis channel groups | `market_prices`, `trades_updates_*` | ACTIVE_TO_MIGRATE | NATS/Centrifugo bridge | NO |
| WebSocket ticket middleware | `FX/ws/channels_auth.py` | ACTIVE_REQUIRED | Centrifugo token service | NO |

Known routes: `/ws/v1/`, `/ws/market-data/`, `/ws/crypto-market-data/`,
`/ws/stock-market-data/`, `/ws/trades/`, `/ws/users/`, `/ws/market/`,
`/ws/v1/real-wallet/`, and user/account portfolio routes. No Centrifugo or NATS
service is present in the current staging compose project.

Unknown/unsafe components are not deleted. A route may only move to
`DISABLED` after access logs show zero use and the replacement passes parity,
security, load and rollback gates.
