# V2 channel registry

The authoritative registry is `FX/ws/v2.py` and is exposed at
`GET /api/v1/realtime/v2/channel-registry` for authenticated staging clients.

Public market/news channels are tenant-scoped and require the corresponding
read permission. Trade, order, portfolio and wallet channels are private and
must contain the authenticated account identifier. Notification and security
channels must contain the authenticated user identifier. Unknown channel
shapes are rejected before a subscription token is issued.

Every event envelope carries `event_id`, `schema_version`, `channel`,
`sequence`, `timestamp`, `source`, and `payload`. Consumers reject duplicates
and out-of-order events and recover a sequence gap from the snapshot provider.
