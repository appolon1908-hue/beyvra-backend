# Isolated Simulation Capacity Certification

Measured 2026-08-11 on the authorized host using disposable PostgreSQL 16 and
Redis, Python 3.11 application image, and no staging traffic or external providers.
These results are not production capacity claims.

| Profile | Concurrency | Completed | Errors | Throughput | Order p95/p99 | Execution/settlement p95/p99 |
|---|---:|---:|---:|---:|---:|---:|
| 100 workflows | 10 | 100 | 0 | 17.50/s | 580.9/789.7 ms | 621.9/770.5 ms |
| 1,000 workflows | 20 | 1,000 | 0 | 29.30/s | 703.6/1034.0 ms | 725.4/1036.9 ms |
| 10,000 workflows | prepared, not executed | — | — | — | — | — |

The mix exercised preview, create, full fill, partial fill, cancel, reservation,
settlement, position, audit, idempotency and outbox writes. The 1,000 profile created
1,000 orders/reservations/trades and 3,300 order-scoped outbox events. Existing
isolated tests also certified 100 concurrent identical keys: one order and one
reservation.

| Realtime clients | Connected | Failures/gaps | Connect p95/p99 |
|---:|---:|---:|---:|
| 100 | 100 | 0/0 | 89.6/90.8 ms |
| 500 | 500 | 0/0 | 251.3/255.8 ms |
| 1,000 | 1,000 | 0/0 | 419.4/426.3 ms |

Likely bottleneck: serialized account/reservation/position locks; latency roughly
doubled from concurrency 10 to 20 while throughput increased 67%. Recommended
initial staging guardrail is <=20 concurrent simulated workflow workers and <=500
new realtime connections in a burst. Treat sustained order p95 >750 ms, p99 >1 s,
any error, or growing outbox/consumer lag as the unsafe threshold. CPU/memory and
DB-pool series require the new private scrape deployment before higher certification.
