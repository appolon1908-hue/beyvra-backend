# Chaos Observability Contract

Every isolated scenario sets `beyvra_chaos_fault_active`, records recovery duration,
and preserves invariant counters at zero. Expected additional signals:

| Scenario family | Fault signal | Recovery signal |
|---|---|---|
| OUTBOX_WORKER_KILL | worker up=0; pending/age rise | heartbeat returns; backlog drains |
| EXECUTION_CONSUMER_KILL | worker up=0; lag rises | lag drains; duplicate effects=0 |
| REDIS_OUTAGE | Redis up=0; errors rise | up=1; reconnect rises; API recovers |
| NATS_OUTAGE / JETSTREAM_REDELIVERY | NATS up=0 or lag/redeliveries rise | stream/consumer available; lag drains |
| REALTIME_BRIDGE_KILL / CENTRIFUGO_OUTAGE | realtime up=0; publish failures | up=1; snapshot recovery succeeds |
| DATABASE_SESSION_KILL | DB errors/rollbacks rise | DB up=1; transaction retry succeeds |
| API_WORKER_KILL | backend up=0; request failures | readiness and availability recover |
| NETWORK_PARTITION | affected dependency down | connectivity restored; no rules remain |
| CANCEL_FILL_RACE / PARTIAL_FILL_REORDER | contention/redelivery may rise | invariants zero; final projection reconciles |
| IDEMPOTENCY_STORM | replay count rises | one order; conflict counted; no duplicate effect |
| ENDURANCE_CHAOS | latency/retry/recovery series | workload ends; backlog zero; invariants zero |

An alert test must prove fire, healthy silence, and resolution using isolated synthetic
metrics. Staging chaos remains prohibited.
