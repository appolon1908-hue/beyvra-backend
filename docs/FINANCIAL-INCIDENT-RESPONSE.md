# Financial incident response

Incident types include unknown outcome, duplicate effect, reconciliation mismatch, provider incident and withdrawal-security incident. Evidence records severity, type, detection time, candidate SHA, environment, safe summary, status, resolution time and evidence hash.

Logical halt states are `ACTIVE`, `READ_ONLY`, `WITHDRAWALS_HALTED`, `FUNDING_HALTED`, `ALL_MUTATIONS_HALTED`. These can only reduce capability; disabled real-money flags always win. Preserve evidence, stop affected workflows, query authoritative state, reconcile, and require independent approval before recovery.
