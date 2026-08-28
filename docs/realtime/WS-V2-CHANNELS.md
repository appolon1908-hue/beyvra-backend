# V2 channel registry

The authoritative registry is `FX/ws/v2.py` and is exposed at
`GET /api/v1/realtime/v2/channel-registry` for authenticated staging clients.

Public market channels are tenant-scoped and require the corresponding read
permission. The currently advertised provider-backed market channels are
`market.{symbol}.quote` and `market.{symbol}.candle.{timeframe}`. News channels
are intentionally absent from the Centrifugo/NATS V2 registry until a genuine
publisher is wired; database-backed news compatibility streaming remains an app
gateway concern. Unsupported market tick, order book, and trade channels are
also intentionally absent until a genuine provider-backed publisher is wired.
Trade, order, portfolio and wallet channels
are private and must contain the authenticated account identifier. Notification
and security channels must contain the authenticated user identifier. Unknown
channel shapes are rejected before a subscription token is issued.

Every event envelope carries `event_id`, `schema_version`, `channel`,
`sequence`, `timestamp`, `source`, and `payload`. Consumers reject duplicates
and out-of-order events and recover a sequence gap from the snapshot provider.
