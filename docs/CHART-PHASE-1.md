# Chart data authority — Phase 1

The trading backend is the sole market-data authority. The chart obtains an initial snapshot from `GET /api/v1/market-data/snapshot`, then consumes the existing `/ws/v2/` runtime. Timeframe changes use `GET /api/v1/market-data/candles`. Instrument metadata and demo-only trading rules are exposed under `/api/v1/instruments/`.

The frontend `ChartDataController` owns HTTP cancellation, quote/candle subscriptions, per-channel sequence tracking, duplicate rejection, gap recovery, candle deduplication, and stale-instrument rejection. Rendering receives state from that controller; drawers, indicators, drawings, zoom, pan, amount, duration, and chart-type controls must never fetch market data or recreate the chart.

## Request invariants

- Instrument change: abort old request, unsubscribe old quote/candle channels, fetch one 500-candle snapshot, subscribe to the new quote/candle channels.
- Timeframe change: unsubscribe the old candle channel, fetch candles once, subscribe to the new candle channel. The quote subscription remains active.
- Older or duplicate sequence: ignore.
- Sequence gap: perform one snapshot recovery and replace local chart state.
- Events and responses for a prior instrument: ignore.

## Safety and current limitations

Provider governance remains authoritative and fail-closed. With no approved provider, snapshot/candle requests return HTTP 503 and make no outbound provider request. Sub-minute intervals are part of the chart contract, but remain unavailable until an approved provider/runtime supplies them; the capability endpoint returns `GENUINE_5S_SOURCE_UNAVAILABLE` and rejects 5s before resolving or contacting a provider. All trading rules report `real_trading_enabled: false`.

Canonical candles use decimal strings, explicit open/close timestamps, completion state, and sequence metadata. Historical requests accept a `before` cursor and return `history_cursor`. Realtime envelopes contain event type/version, channel, instrument, sequence, occurrence/server timestamps, source, and data. The legacy WebSocket gateway also passes through provider governance before opening an outbound provider connection.

This phase does not modify the Financial Service, Financial PostgreSQL, provider approvals, financial flags, NATS, JetStream, or Centrifugo. Indicators, drawing persistence, news markers, countdowns, and payout/range overlays remain subsequent chart-engine work.
