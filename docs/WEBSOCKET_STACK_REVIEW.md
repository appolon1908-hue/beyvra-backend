# WebSocket stack review

## Decision

Keep Django Channels on ASGI and upgrade it explicitly to Channels 4.3.2,
with Daphne 4.2.2 and `channels-redis` 4.2.0. This is the safest maintained
option for Codestra because the existing authentication middleware, Django
tenant queries, channel-layer group sends, legacy consumers and Daphne
deployment already use the ASGI/Channels contract. Channels' current
documentation describes it as Django's ASGI WebSocket integration and lists
Daphne and `channels_redis` as the supported deployment pieces.

FastAPI/Starlette and Socket.IO remain viable for a separate service, but
introducing either here would require a second authentication/session adapter,
tenant authorization implementation, event bridge, deployment surface and
legacy protocol proxy. That would increase migration risk without solving an
existing capability gap.

## Compatibility contract

- New platform clients use `/ws/v1/` with one-time `ws_ticket` authentication.
- The gateway supports `subscribe`, `unsubscribe`, `resume` and `ping`.
- Duplicate subscriptions are acknowledged once and ignored thereafter.
- Channel authorization is tenant/user scoped; provider webhook and payment
  channels are not browser channels.
- Ordered events include `event_id`, `version`, `channel`, `sequence`,
  `occurred_at` and `data`.
- Existing `/ws/market-data/`, `/ws/trades/`, `/ws/users/` and other legacy
  paths remain available until their consumers are migrated and tested.

## Deferred migration work

The gateway currently owns the platform chart feed. Notification, portfolio and
legacy dashboard consumers still use their existing routes. They must be moved
one consumer family at a time with parity tests before those routes are retired.
