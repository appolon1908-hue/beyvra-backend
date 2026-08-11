# Five-second data authority

`5S_AVAILABLE=false` and `FIVE_SECOND_AVAILABLE=False`. The deterministic server aggregator is fixture-certified for genuine ticks, out-of-order delivery, duplicates, late finalized ticks, OHLCV, completeness, and empty intervals. Its existence does **not** activate 5-second data.

Activation requires either provider-native genuine 5s bars or licensed genuine tick/trade input plus an approved runtime aggregation certification. One-minute subdivision, interpolation, polling, randomization, and browser aggregation are prohibited. Current timeframe authority: provider-native `1m`, `5m`, `15m`, `1h`, `4h`, `1d` contracts are fixture-certified; entitlement remains separately governed.

