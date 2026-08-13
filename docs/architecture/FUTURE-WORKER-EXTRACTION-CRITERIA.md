# Future worker extraction criteria

Worker extraction is a separate architecture change and requires a new
authority, migration, event, operational and exact-SHA certification cycle.
It is considered only when measured evidence crosses at least one trigger:

| Domain | Measurable extraction triggers |
|---|---|
| Post-trade | p95 processing latency breaches policy; lock contention; independent retry/failure isolation or autoscaling becomes necessary |
| Valuation | valuation frequency or portfolio size exceeds synchronous capacity; request latency breaches policy; independent scheduling is required |
| Treasury | funding simulation duration or contention breaches policy; independent scheduling/retry/isolation becomes necessary |
| Regulatory records | evidence workload materially delays trading; retention, replay, isolation or independent scaling requires a separate lifecycle |

Before extraction, define queue ownership, transactional outbox/inbox,
idempotency, ordering, replay, reconciliation, dead-letter policy and migration
rollback. No worker may become a second business authority.
