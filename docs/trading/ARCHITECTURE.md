# Trading data architecture

Market data is normalized at the provider boundary into versioned events and
validated by `trade.market_events.SequenceTracker`. PostgreSQL remains the
source of truth for instruments, demo orders, positions, and persisted news.
JetStream is bounded transport/replay infrastructure only. Real execution and
automated news trading remain disabled.
