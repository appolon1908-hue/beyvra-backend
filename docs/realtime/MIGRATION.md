# Realtime migration plan

## Current decision

Keep Django Channels/Daphne as the staging authority while the replacement is
proved. Channels 4.3.2 is explicitly pinned; the current `/ws/v1/` gateway is
the compatibility bridge. Centrifugo and NATS are not yet deployed and are not
represented as healthy.

## Safe order

1. Capture route, dependency, image and proxy backups.
2. Add a private Centrifugo/NATS staging stack with no public broker ports.
3. Add middleware-issued short-lived connection/subscription tokens.
4. Mirror market events and compare sequence, latency and tenant decisions.
5. Migrate one consumer family at a time: market, news, trade/order,
   portfolio, wallet, notifications.
6. Disable legacy routes behind staging flags and observe zero traffic.
7. Run security, recovery, load, accessibility and full E2E suites.
8. Keep rollback images and re-enable legacy routes on any failed gate.
9. Delete only after all deletion-gate conditions are evidenced.

## Deletion policy

`LEGACY_SOCKET_CODE_DELETION_APPROVED` remains false. No legacy socket,
consumer, chart adapter or dependency is removed by this migration checkpoint.
