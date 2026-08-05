# Realtime V2 production-certification checklist

Scope is staging only. `/ws/v1/` remains the rollback path and no production,
payments, live trading, or real-money flags are changed.

## Completed

- NATS JetStream is pinned, private, persistent, and healthy.
- NATS server TLS and client-certificate verification are enabled.
- Centrifugo and the realtime bridge use separate staging client identities.
- A client without a certificate is rejected; an authorized client publishes successfully.
- NATS restart restores streams and consumers.
- Centrifugo and bridge restart successfully after NATS recovery.
- Nginx restart completed and the container returned healthy.
- Backend system checks and V2 contract tests pass.
- Prometheus alert rules and a Grafana dashboard definition are checked into `monitoring/`.

## Open gates

- Dedicated-host 500+ connection test (the previous staging-edge run did not meet 100%).
- The public staging endpoint currently returns `404` for the expected guest-session probe;
  a reachable authorized load endpoint is required before an external V2 load run.
- Token replay, privilege downgrade, and full cross-tenant/workspace matrix.
- 1-hour endurance, followed by 4-hour endurance only if the first passes.
- Complete event-loss/duplicate detection under restart and reconnect storms.
- Prometheus/Grafana deployment and alert firing evidence.

The release status remains `PARTIAL_BLOCKED` until every open gate has evidence.
