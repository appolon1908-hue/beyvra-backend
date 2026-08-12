# Market-data freshness

Freshness uses the larger of `now-provider_timestamp` and `now-received_at`; neither clock is rewritten. Thresholds are policy inputs by provider/data type/asset class and yield `FRESH`, `DEGRADED`, `STALE`, or `UNAVAILABLE`. Cached values must carry `stale=true` when outside policy. Simulated preview/create must call the freshness gate and reject stale/unavailable authority with `MARKET_DATA_STALE`. Real trading stays disabled independently. Future timestamps and clock skew are anomaly signals, not corrected timestamps.

