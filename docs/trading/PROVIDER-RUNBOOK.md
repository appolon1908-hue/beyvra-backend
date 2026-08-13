# Provider runbook

If a provider is delayed, rate-limited, unavailable, or license-blocked, stop
the live indicator, expose source and freshness, retain safe historical cache,
and open a staging incident. Reconnect with bounded backoff and recover gaps
through snapshot/replay. Never silently fail over or synthesize market data.
