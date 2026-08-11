# Isolated Simulation Capacity Certification

Measured 2026-08-11 on the authorized host using disposable PostgreSQL 16 and
Redis, Python 3.11 application image, and no staging traffic or external providers.
These results are not production capacity claims.

| Profile | Concurrency | Completed | Errors | Throughput | Order p95/p99 | Execution/settlement p95/p99 |
|---|---:|---:|---:|---:|---:|---:|
| 100 workflows | 10 | 100 | 0 | 17.50/s | 580.9/789.7 ms | 621.9/770.5 ms |
| 1,000 workflows | 20 | 1,000 | 0 | 29.30/s | 703.6/1034.0 ms | 725.4/1036.9 ms |
| 10,000 workflows | 20 | 10,000 | 0 | 19.71/s | 2532.9/3646.9 ms | 2673.3/3859.5 ms |

The mix exercised preview, create, full fill, partial fill, cancel, reservation,
settlement, position, audit, idempotency and outbox writes. The 1,000 profile created
1,000 orders/reservations/trades and 3,300 order-scoped outbox events. Existing
isolated tests also certified 100 concurrent identical keys: one order and one
reservation.

The 10,000 profile completed in 507.244 seconds and created 10,000 orders,
reservations and trades plus 33,000 outbox events. Preview p50/p95/p99 was
36.5/90.8/118.6 ms; order/outbox was 200.7/2532.9/3646.9 ms; and
execution/settlement was 283.2/2673.3/3859.5 ms. A post-load full read-only
reconciliation passed 11 applicable checks with zero violations and PostgreSQL
reported zero deadlocks.

Sampled resource peaks were 125.8% CPU and 203.3 MiB for the Python runner,
123.1% CPU and 143.1 MiB for PostgreSQL, and 5.4% CPU and 6.2 MiB for Redis.
PostgreSQL peaked at 27 of 100 sessions in the samples (27% occupancy, 73%
connection headroom). These sampled—not continuous—peaks on a 62.6 GiB host are
not production capacity evidence.

| Realtime clients | Connected | Failures/gaps | Connect p95/p99 |
|---:|---:|---:|---:|
| 100 | 100 | 0/0 | 89.6/90.8 ms |
| 500 | 500 | 0/0 | 251.3/255.8 ms |
| 1,000 | 1,000 | 0/0 | 419.4/426.3 ms |

Likely bottleneck: serialized account/reservation/position locks and PostgreSQL CPU,
not connection capacity. The 10,000 batch at concurrency 20 breached the initial
750 ms order p95 target despite zero errors. Recommended initial staging guardrail
is <=10 concurrent simulated workflow workers, with a controlled test required before
raising it, and <=500 new realtime connections in a burst. Treat sustained order p95
>750 ms, p99 >1 s, any error, or growing outbox/consumer lag as unsafe. Private
node/cAdvisor/PostgreSQL/Redis/NATS scraping is now deployed; future runs should use
continuous Prometheus range data rather than sampled peaks.
