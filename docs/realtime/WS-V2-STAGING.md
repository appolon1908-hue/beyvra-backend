# Codestra realtime V2 staging

V2 is a staging-only migration path from `/ws/v1/` to `/ws/v2/`. The browser
connects to the Centrifugo WebSocket endpoint behind the stable public prefix
`/ws/v2/connection/websocket`. Centrifugo authenticates short-lived JWTs from
the middleware and delegates subscription authorization to the private
middleware proxy. NATS JetStream is private and carries normalized event
envelopes; PostgreSQL remains authoritative for orders, trades, wallets and
audit records.

## Services

| Service | Version | Exposure | Purpose |
|---|---|---|---|
| NATS | 2.10.22-alpine | Docker network only | JetStream streams and durable consumers |
| Centrifugo | 6.2.0 | TLS reverse proxy at `/ws/v2/` | Browser connections, broker fan-out |
| `realtime_v2_bridge` | staging backend image | Docker network only | Validated JetStream envelopes to Centrifugo API |

No NATS client or monitoring port is published. Centrifugo admin is disabled.
V1 remains enabled for rollback.

## Security

`connection-token` and `subscription-token` are authenticated Django endpoints.
Claims include user, tenant, workspace, account scope, channel patterns,
expiry, nonce, session and token version. The subscribe proxy re-checks the
channel against the authenticated Centrifugo user and rejects unknown,
cross-account and private-channel mismatches. Proxy traffic is private and
uses a staging secret. No token is placed in a URL.

## Streams

`MARKET_TICKS`, `MARKET_QUOTES`, `MARKET_CANDLES`, `MARKET_ORDERBOOK`,
`MARKET_TRADES`, `NEWS_EVENTS`, `PRIVATE_ACCOUNT_EVENTS`, and `SYSTEM_EVENTS`
are file-backed with bounded 24-hour retention, duplicate windows and a
maximum message size. Stream configuration is recreated only with an explicit
staging backup and rollback point.

## Rollback

Set `REALTIME_V2_ENABLED=false` and keep `REALTIME_V2_STAGING_ENABLED=false`,
restart the frontend/backend services with the preserved V1 images, and route
the browser to `/ws/v1/`. Do not remove V2 containers or JetStream data until
the observation window and migration review are complete.
