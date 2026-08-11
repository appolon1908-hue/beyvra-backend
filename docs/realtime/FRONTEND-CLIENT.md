# Frontend realtime client

The platform chart currently uses the canonical gateway path `/ws/v1/` and
one subscription for the selected candle channel. The remaining legacy
notification/portfolio hooks are inventoried and must be migrated through a
shared connection manager before legacy code can be disabled.
