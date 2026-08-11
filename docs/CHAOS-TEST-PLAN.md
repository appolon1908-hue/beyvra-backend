# Simulated Trading Chaos Test Plan

## Safety boundary

The harness runs only with `BEYVRA_CHAOS_ISOLATED=1` on the internal
`beyvara-chaos_chaos` Docker network. PostgreSQL 16 has no published host port.
Redis, NATS/JetStream, Centrifugo, and Python 3.11 are disposable. The safety gate
rejects staging/production strings and any real-trading, external-execution, or
real-money flag. Financial Service credentials are neither accepted nor mounted.

## Scenario matrix

| Scenario | Fault | Expected behavior / recovery condition |
|---|---|---|
| OUTBOX_WORKER_KILL | kill before/after claim, publish, or completion mark | lease recovery; eventual publication; one business effect |
| EXECUTION_CONSUMER_KILL | crash around transaction and ACK | atomic rollback or committed deduplicated replay |
| REDIS_OUTAGE | disconnect runner and Redis | bounded failure; reconnect; safe response |
| NATS_OUTAGE / JETSTREAM_REDELIVERY | disconnect/restart and redeliver | durable replay; consumer deduplication |
| REALTIME_BRIDGE_KILL / CENTRIFUGO_OUTAGE | stop realtime components | gap detected; canonical snapshot replaces state; resume cursor |
| DATABASE_SESSION_KILL | terminate session/rollback/deadlock | no partial effects; retry after rollback |
| API_WORKER_KILL | stop worker during request | idempotent client retry |
| NETWORK_PARTITION | disconnect approved internal pair | exit trap reconnects; zero remaining rules |
| CANCEL_FILL_RACE | concurrent terminal transitions | one valid final state; no double release/settlement |
| PARTIAL_FILL_REORDER | duplicate, delay, reorder fills | expected total; execution-ID dedupe |
| IDEMPOTENCY_STORM | 100 identical requests | one order/reservation; changed payload returns 409 |
| ENDURANCE_CHAOS | 100/1,000/10,000 workflows | record throughput, failure/retry/recovery/deadlock and p50/p95/p99 |

Every scenario executes setup, baseline verification, injection, fault verification,
workload, recovery, recovery verification, reconciliation, and unconditional cleanup.
Certification deliberately corrupts a snapshot to prove false PASS is impossible.

Run `./chaos/bin/chaos-harness certify`. Staging prerequisites, if separately
authorized later, are an approved window, backups, observability, rollback owner,
tenant fixtures, and explicit endpoint allow-list. This plan does not authorize it.
