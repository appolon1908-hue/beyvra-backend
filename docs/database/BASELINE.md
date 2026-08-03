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
pg_stat_statements: unavailable (extension not installed)
```

Largest tables are `notifications_notificationevent` (24 MB / 59,242 rows) and `trade_marketcandle` (552 kB / 1,552 rows). The staging dataset is too small to justify production-like partitioning benchmarks; migration tests must use synthetic volume before selecting partition granularity.

## Immediate evidence gaps

1. Enable `pg_stat_statements` only in disposable/staging first, then collect query totals, plans, I/O timing, blocked queries and connection utilization.
2. Capture `pg_stat_user_indexes`, duplicate/unused index candidates, and `pg_stat_activity` during representative dashboard and WebSocket workloads.
3. Measure provider tick rate, connected clients, symbols per client, retention volume and worker throughput before setting `work_mem`, connection pools, partitions or retention.

