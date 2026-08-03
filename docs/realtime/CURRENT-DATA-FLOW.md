# Current data flow and target boundary

## Current flow

```text
Browser
  ├── REST market history ──> Django trade/Alpaca/Binance/Twelve Data code
  ├── REST news ────────────> Django NewsData.io wrapper
  └── legacy Channels WS ───> Daphne consumers

Celery/periodic scripts ──> provider REST calls ──> Redis cache / PostgreSQL
```

The browser does not currently connect directly to provider credentials, which is the correct security boundary. However, provider normalization and transport responsibilities are distributed across legacy modules, and news has no internal WebSocket broadcast path.

## Target flow

```text
Provider adapters -> normalizers -> Redis Streams -> persistence/candle workers
                                      └────────────> market/news broadcasters
                                                    └── authenticated /ws/v1/*
```

Market data and news must remain separate logical channels. Account and platform events must not share the public market socket.

## Required durable state

The target design needs provider-neutral instruments, provider connections, normalized candles/news/economic events, offsets, dead-letter records, and WebSocket audit records. High-volume raw ticks must be retained in time partitions or a bounded raw-event store rather than the existing transactional tables.

