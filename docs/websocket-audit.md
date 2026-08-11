# WebSocket audit

All application WebSockets are served by Django Channels through `FX.asgi` and
authenticated by a short-lived, one-time `ws_ticket` query parameter. Missing,
expired, invalid, or already-consumed tickets are anonymous and protected
consumers close with code `4401`.

| Route | Consumer | Purpose | Access |
| --- | --- | --- | --- |
| `/ws/market-data/` | `LiveMarketDataConsumer` | Normalized live crypto candles | Authenticated |
| `/ws/external-api/` | `WebsocketConsumer` | Legacy wallet/trade/online events | Authenticated |
| `/ws/current-balance/<user_id>/` | `CurrentBalanceConsumer` | Account balance | Same user only |
| `/ws/profit-loss/<user_id>/` | `ProfitLossConsumer` | Portfolio profit/loss | Same user only |
| `/ws/asset-data/<user_id>/` | `AssetConsumer` | Portfolio holdings | Same user only |
| `/ws/crypto-market-data/` | `CryptoMarketDataConsumer` | Legacy Polygon crypto snapshot | Authenticated |
| `/ws/stock-market-data/` | `StockMarketDataConsumer` | Legacy Polygon stock snapshot | Authenticated |
| `/ws/market/` | `MarketDataConsumer` | Internal market event groups | Authenticated |
| `/ws/trades/` | `TradeConsumer` | User-scoped trade events | Authenticated |
| `/ws/users/` | `UserConsumer` | User notifications | Authenticated |
| `/ws/admin/` | `AdminDataConsumer` | Administrative events | Staff only |

## Providers

The primary staging live-price route uses Binance's public `kline` WebSocket.
Its REST counterpart backfills and caches normalized candles in PostgreSQL.
The two legacy grouped-market routes use Polygon and require
`POLYGON_API_KEY`; they should not be treated as active without that credential.
Alpaca settings and scripts exist for order/news integrations but do not supply
the primary dashboard candle stream.

## Edge routing

Caddy routes `/ws/*` directly to the backend Nginx service. Caddy's
`reverse_proxy` supports WebSocket upgrade automatically. Backend Nginx then
forwards the upgraded connection to Daphne. REST `/api/*` follows the same edge
path, while all other staging traffic is handled by the frontend container.
