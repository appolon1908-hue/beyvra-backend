# Provider failover

Each instrument/data type requires explicit primary, secondary, `failover_allowed`, switch delay, and normalization compatibility. States are `PRIMARY_LIVE`, `PRIMARY_DEGRADED`, `FAILOVER_PENDING`, `SECONDARY_LIVE`, and `NO_AUTHORITY`. The selector accepts events only from the single authoritative provider, preventing split brain. It never mixes quotes/trades/candles across providers and never changes commercial priority automatically. Switches preserve provenance and increment an observable failover event/metric. Snapshot/stream reconciliation uses provider/data-type tolerances; sequence gaps degrade the feed and require an authoritative snapshot rebuild where supported.

