# Canonical API and Realtime Compatibility

## Authority

Customer HTTP integrations use `/api/v1/*`. Customer realtime uses `/ws/v2/`.
The authenticated principal in the server-side socket scope is authoritative;
private channel authorization never trusts a caller-supplied user identifier.

## Compatibility

`/api/user/*`, `/api/notification/*`, and `/ws/v1/` remain temporary wrappers
over the same views/consumer. They do not own separate business logic. Legacy
HTTP responses include `Deprecation`, `Sunset`, and successor `Link` metadata.
The v1 gateway ready frame identifies `/ws/v2/` as its successor.

Usage is measured by:

- `legacy_api_requests_total{route,client_version,environment}`
- `legacy_ws_connections_total{route,client_version,environment}`

Removal requires zero observed staging usage, production usage evidence, and a
separate retirement review. No compatibility route is removed by this change.

## Safety

Real wallet reads and every real-money mutation remain disabled. Provider and
external execution activation are outside this change. The Financial Service
and production are unchanged.
