# Service health authority

`/health` is process liveness only. `/ready` checks PostgreSQL, Redis, and—when enabled—the durable outbox publisher heartbeat. Customer status and capability endpoints expose no topology. Operator APIs expose bounded dependency evidence. Health states are `HEALTHY`, `DEGRADED`, `UNHEALTHY`, and `UNKNOWN`; an empty or unknown critical registry is unhealthy.
