# Realtime Event Protocol & Gap Recovery

## Event Envelope Schema (v1.0)
```json
{
  "schema_version": "1.0",
  "event_id": "<uuid>",
  "event_type": "order.updated",
  "tenant_id": "<uuid>",
  "account_id": "<uuid>",
  "aggregate_id": "<uuid>",
  "aggregate_version": 4,
  "sequence": 1042,
  "occurred_at": "2026-08-28T00:00:00Z",
  "published_at": "2026-08-28T00:00:00Z",
  "request_id": "<uuid>",
  "data": {}
}
```

## Supported Event Channels
- `price.updated`
- `candle.updated`
- `order.updated`
- `execution.created`
- `position.updated`
- `balance.updated`
- `compliance.restriction.updated`
- `system.degraded`
- `system.recovered`

## Authentication & Ticket Flow
1. Client requests an ephemeral, single-use ticket: `POST /api/v1/realtime/ticket`.
2. Connects to WebSocket passing ticket token.
3. Subscriptions are authorized strictly based on server-side session credentials.

## Gap Recovery Sequence
1. Upon reconnect, client invokes: `GET /api/v1/realtime/resume?after_sequence={sequence}`.
2. If sequence is within sliding memory buffer -> Missed events are streamed.
3. If sequence gap exceeds buffer threshold -> Server returns `409 SNAPSHOT_REQUIRED`.
4. Client requests full state snapshot: `GET /api/v1/realtime/snapshot` and resets baseline.
