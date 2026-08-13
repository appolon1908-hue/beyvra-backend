# Chaos and recovery matrix

This matrix supersedes checklist language that assumed every domain was a
standalone process. Faults target the deployed boundary.

| Component | Deployment model | Fault injection method | Recovery test | Invariants / pass criteria |
|---|---|---|---|---|
| API | standalone process | stop/restart API container | readiness and canonical request after restart | committed data retained; API recovers |
| Outbox | standalone worker | stop publisher with committed events | restart and drain | no lost committed outbox events or duplicate effects |
| Execution | standalone consumer | stop consumer with queued simulated order | restart and consume | one fill/trade; valid order state |
| Realtime bridge | standalone process | stop bridge during activity | restart, detect gap, snapshot and resume | no authoritative data loss |
| Redis | dependency | bounded stop/restart | fail-closed degradation and readiness recovery | no security fail-open |
| NATS | dependency | bounded stop/restart | outbox retention and reconnect | no committed-event loss |
| JetStream consumer | durable consumer | stop/restart execution consumer | redelivery | one business effect |
| PostgreSQL | dependency | terminate selected sessions | reconnect and reconcile | atomic rollback; no partial truth |
| Post-trade | synchronous | transaction failure, duplicate fill, delayed outbox | replay and `reconcile_post_trade` | no duplicate/lost trade or settlement intent |
| Valuation | synchronous | stale price, calculation exception, transaction rollback | deterministic recompute and `ValuationReconciler` | position and P&L reconcile; no duplicate effect |
| Treasury | synchronous simulation | calculation error, rollback, duplicate plan request | idempotent recompute and invariant inspection | no duplicate plan; zero real transfers |
| Regulatory records | synchronous evidence authority | rollback, duplicate request, evidence-hash mismatch | replay and compliance/surveillance reconciliation | no gaps/duplicates; append-only audit intact |
| Network | isolated staging | disconnect execution consumer network | reconnect and drain | queued order reaches one terminal result |
| Endurance | isolated staging | bounded sustained simulated workload | reconciliation and resource snapshot | no backlog/invariant failure |

`CHAOS_MATRIX_MATCHES_REAL_ARCHITECTURE=YES`

Canonical recovery gates use `POST_TRADE_FAILURE_RECOVERY`,
`VALUATION_FAILURE_RECOVERY`, `TREASURY_FAILURE_RECOVERY`, and
`REGULATORY_FAILURE_RECOVERY`. The obsolete `*_WORKER_RECOVERY` labels do not
apply to these four synchronous domains.
