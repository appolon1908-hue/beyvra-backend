# PostgreSQL baseline

Captured 2026-08-03 against `tradi_staging`. No settings were changed.

## Capacity

```text
20 logical CPUs / 14 physical cores
62 GiB RAM
RAID1 NVMe-backed 436 GB root volume, 38% used
PostgreSQL shares the host with application, Redis, workers and observability
```

## Database state

```text
database size: 37 MB
current migration heads:
  integrations.0002_credential_encryption
  notifications.0007_webhook_secret_encryption
pg_stat_statements was unavailable at initial capture. It is now enabled in staging only (`shared_preload_libraries=pg_stat_statements`, `pg_stat_statements.track=all`, `track_io_timing=on`, `log_min_duration_statement=500`) and the extension is installed. A representative dashboard/WebSocket workload is still required before using query totals for tuning. The first post-enable sample contains only setup statements and is not a tuning signal.
```

Largest tables are `notifications_notificationevent` (24 MB / 59,242 rows) and `trade_marketcandle` (552 kB / 1,552 rows). The staging dataset is too small to justify production-like partitioning benchmarks; migration tests must use synthetic volume before selecting partition granularity.

## Immediate evidence gaps

1. Exercise representative dashboard and WebSocket workloads, then collect query totals, plans, I/O timing, blocked queries and connection utilization.
2. Capture `pg_stat_user_indexes`, duplicate/unused index candidates, and `pg_stat_activity` during representative dashboard and WebSocket workloads.
3. Measure provider tick rate, connected clients, symbols per client, retention volume and worker throughput before setting `work_mem`, connection pools, partitions or retention.

## Index, activity, and Redis sample

- The least-used indexes are predominantly small Django uniqueness/lookup
  indexes. `trade_marketcandle.unique_market_candle` is 120 kB and had zero
  scans in this idle sample; it must not be dropped without a captured query
  plan.
- There were no user queries running at capture time; only PostgreSQL
  background workers were present in `pg_stat_activity`.
- Redis 7.4.10 is standalone with approximately 2.00 MiB used memory, no
  configured maxmemory, `noeviction`, RDB persistence enabled, and AOF disabled.
  This is acceptable for the current small staging cache but is not yet a
  durable Streams production profile.
