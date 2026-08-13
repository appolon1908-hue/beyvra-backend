# Realtime and database discovery baseline

Captured 2026-08-03 from the staging deployment. This is measurement only; no PostgreSQL tuning or external provider activation was performed.

## Host

| Measurement | Value |
|---|---|
| CPU | Intel 13th Gen i5-13500, 20 logical CPUs, 14 cores, one socket |
| RAM | 62 GiB total, 47 GiB available at capture |
| Swap | 31 GiB total |
| Storage | Two 476.9 GB NVMe devices in RAID1; root `/dev/md2`, 436 GB, 38% used |
| Docker | PostgreSQL, Redis, web, Daphne, Celery and monitoring share the host |

## Runtime versions

| Component | Version |
|---|---|
| PostgreSQL | 16.14 |
| Redis | 7.4.10 |
| Django | 5.2.16 |
| Channels | 4.2.2 |
| Daphne | 4.2.2 |

## PostgreSQL configuration

The active values are still mostly defaults:

```text
max_connections=100
shared_buffers=128MB
effective_cache_size=4GB
work_mem=4MB
maintenance_work_mem=64MB
wal_buffers=4MB
checkpoint_completion_target=0.9
random_page_cost=4
effective_io_concurrency=1
max_worker_processes=8
max_parallel_workers=8
max_parallel_workers_per_gather=2
autovacuum=on
autovacuum_max_workers=3
autovacuum_naptime=60s
```

`pg_stat_statements` is not installed or preloaded. Query-topology tuning is therefore not yet evidence-based. The extension and preload change must be applied in a disposable/staging PostgreSQL instance first.

## Database size and activity

```text
Database: tradi_staging
Size: 37 MB
Largest table: notifications_notificationevent, 24 MB, 59,242 live rows, 1,166 dead rows
Second largest: trade_marketcandle, 552 kB, 1,552 live rows, 109 dead rows
```

Observed high sequential scans include `users_user` (140,145 scans / 312 index scans) and `notifications_notifications` (72,156 scans / 0 index scans). These require query-plan inspection before adding indexes; scan counts alone are not proof of a missing index.

## Existing realtime/provider implementation

The backend currently exposes legacy Channels routes including `/ws/market-data/`, `/ws/market/`, `/ws/users/`, `/ws/trades/`, balance/profit-loss routes, and external API routes. There is no `/ws/v1/market-data` or `/ws/v1/news` contract yet.

Existing provider code is mixed: Binance REST for crypto candles, Twelve Data REST settings for selected symbols, Alpaca scripts, Polygon calls in portfolio consumers, and NewsData.io REST for news. Credentials are backend settings only. There is no provider-neutral adapter layer, durable Redis Stream ingestion, sequence-aware broadcaster, or news WebSocket.

## Safety state

The following remain disabled:

```text
MARKET_DATA_ENABLED=false
NEWS_STREAM_ENABLED=false
ECONOMIC_EVENTS_ENABLED=false
real external delivery=disabled
production deployment=not authorized
```
