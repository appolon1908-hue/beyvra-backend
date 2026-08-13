# Realtime channels

The `/ws/v2/` contract is consumed through a unified realtime client. Market
channels are `market.{symbol}.tick`, `.quote`, `.candle.{timeframe}`,
`.orderbook`, `.trades`, and `.status`; news and demo channels are separate.

Every event carries an ID, schema version, ISO timestamp, and monotonic
sequence. Duplicate and out-of-order events are rejected. Gaps request a
bounded snapshot before replay resumes; stale feeds are surfaced rather than
presented as live.
