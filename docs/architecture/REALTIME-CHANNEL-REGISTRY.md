# Realtime Channel Registry

Public WebSocket endpoint: `/ws/v2/`. `/connection/websocket` is an internal Centrifugo upstream and is never a browser contract.

The only canonical market dialect is dotted, symbol-first V2 (`market.{symbol}.<kind>`). Colon-form and `market.compat.*` channels are deprecated and are not accepted by the V2 registry.
News channels are intentionally not advertised by the Centrifugo/NATS V2 token
registry until a durable publisher owns them. The app gateway may expose
database-backed compatibility news subscriptions separately.

| Name | Schema | Producer | Consumer | Tenant scope | Account scope | Replay | REST recovery endpoint |
|---|---:|---|---|---|---|---|---|
| `market.{symbol}.quote` | 1 | market data authority | public clients | yes | no | 100 / 30s | `/api/v1/market-data/snapshot` |
| `market.{symbol}.candle.{timeframe}` | 1 | market data authority | public clients | yes | no | 500 / 300s | `/api/v1/market-data/snapshot` |
| `simulation.order.{account_id}` | 1 | trading outbox bridge | account clients | yes | yes | 100 / 300s | `/api/v1/trading/orders` |
| `simulation.execution.{account_id}` | 1 | trading outbox bridge | account clients | yes | yes | 100 / 300s | `/api/v1/trading/trades` |
| `simulation.position.{account_id}` | 1 | trading outbox bridge | account clients | yes | yes | 100 / 300s | `/api/v1/trading/positions` |
| `simulation.execution-quality.{account_id}` | 1 | execution authority | account clients | yes | yes | 100 / 300s | `/api/v1/execution/reports` |
| `notification.{user_id}` | 1 | notification authority | user clients | yes | yes | 100 / 300s | `/api/v1/notifications/` |
| `account.security.{user_id}` | 1 | account security authority | user clients | yes | yes | 100 / 300s | `/api/v1/session` |
| `treasury.{tenant_id}` | 1 | treasury simulation read model | tenant clients | yes | no | 100 / 300s | `/api/v1/treasury/liquidity` |
| `institutional.subaccount.updated.v1.{user_id}` | 1 | institutional projection | institutional user clients | yes | yes | 100 / 300s | `/api/v1/institutional/account/hierarchy` |
| `system.status` | 1 | platform operations | public clients | no | no | none | `/api/v1/realtime/v2/health` |

Legacy direct-gateway demo channels are retired and are not accepted by new frontend subscriptions.
