# Demo event producer

Demo order state and `trade_demoeventoutbox` records commit in the same application PostgreSQL transaction. The publisher sends only committed rows to the existing `PRIVATE_ACCOUNT_EVENTS` JetStream using `Nats-Msg-Id` deduplication; the existing realtime bridge forwards the validated envelope to Centrifugo.

Events are private and account scoped:

- `demo.order:{wallet_id}` via `private.order.{wallet_id}`
- `demo.execution:{wallet_id}` via `private.trade.{wallet_id}`

The subscription authorization endpoints verify that the authenticated user owns the non-real wallet. Global demo channels are intentionally not published because they would disclose one account's trade state to other subscribers.

Supported producer events are `demo.order.accepted`, `demo.order.rejected`, `demo.order.cancelled`, `demo.order.expired`, `demo.execution.opened`, and `demo.execution.settled`. Event IDs are unique, schema version is explicit, and the outbox primary key supplies the monotonic sequence. Open, expiry, settlement timestamps, and settlement prices originate on the server.

`GET /api/v1/demo/trades` returns `{results, next_cursor, limit}`. The default limit is 25 and the maximum is 100. `status=active,recent` is the default bounded filter.

## Operations

The `demo-event-publisher` Compose service runs `python manage.py publish_demo_events`. A one-shot recovery run is:

```sh
docker compose -f docker-compose.yaml run --rm demo-event-publisher python manage.py publish_demo_events --once
```

Pending rows remain recoverable after NATS or bridge failure. Do not manually mark rows published. Do not publish demo events to an unscoped Centrifugo channel.

## Rollback

Stop the publisher first, deploy the previous backend image, then reverse only migration `trade.0011` if and only if its outbox contains no evidence that must be retained:

```sh
docker compose -f docker-compose.yaml stop demo-event-publisher
docker compose -f docker-compose.yaml run --rm web python manage.py migrate trade 0010
```

The pre-change bundle, application database dump, runtime configuration, image IDs, and checksums are stored under `/root/backups/codestra-demo-producer-20260807T021000Z/` on staging.

## Frozen-client limitation

Frontend candidate `cd00beebd56c9ec5270606f6a7e379b86735599d` subscribes to unscoped `demo.order` and `demo.execution`. Those names cannot safely carry private events over Centrifugo. A separately reviewed frontend candidate must subscribe using the bootstrap account ID before V2 end-to-end certification can pass.
