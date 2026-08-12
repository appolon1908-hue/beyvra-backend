# Processing and worker deployment model

## Release decision

The current simulated, fail-closed release executes post-trade, valuation,
treasury, and regulatory evidence logic in the application process. These
domains are not independently deployed queues or workers. A request, simulated
execution consumer, or explicitly invoked reconciliation command calls their
service layer directly.

`STANDALONE_WORKER_REQUIRED_FOR_CURRENT_RELEASE=NO` applies to every domain
below. Process-kill certification is only meaningful for the API, outbox
publisher, execution consumer, realtime bridge, Redis, NATS/JetStream, and
PostgreSQL boundaries that actually exist.

## POST_TRADE

- `CURRENT_EXECUTION_MODEL=IN_PROCESS_SYNCHRONOUS`
- `PROCESS_BOUNDARY=application process handling canonical simulated fill`
- `TRANSACTION_BOUNDARY=process_simulated_fill transaction.atomic`
- `FAILURE_BOUNDARY=fill transaction, PostgreSQL, outbox publication after commit`
- `RETRY_MODEL=replay canonical execution identity; duplicate capture returns existing trade`
- `IDEMPOTENCY_MODEL=unique execution identity and get-or-create settlement intent`
- `RECONCILIATION_MODEL=PositionReconciler plus canonical trading reconciliation`
- `OBSERVABILITY=post-trade audit, outbox, reconciliation counters and evidence`
- `SCALING_LIMIT=request/consumer latency and database transaction duration`
- `FUTURE_EXTRACTION_TRIGGER=sustained latency, lock contention, independent retry or autoscaling requirement`
- `STANDALONE_WORKER_REQUIRED_FOR_CURRENT_RELEASE=NO`

Failure certification injects transaction failures, duplicate fill delivery,
delayed outbox publication, and replay followed by reconciliation. Killing a
standalone post-trade worker is impossible because no such deployment exists.

## VALUATION

- `CURRENT_EXECUTION_MODEL=IN_PROCESS_SYNCHRONOUS_READ_MODEL`
- `PROCESS_BOUNDARY=application valuation/accounting service invocation`
- `TRANSACTION_BOUNDARY=calling trade transaction or atomic valuation service operation`
- `FAILURE_BOUNDARY=stale/missing market data, calculation error, PostgreSQL transaction`
- `RETRY_MODEL=recalculate deterministically from canonical position effects and prices`
- `IDEMPOTENCY_MODEL=canonical trade basis and evidence-backed snapshots`
- `RECONCILIATION_MODEL=ValuationReconciler`
- `OBSERVABILITY=valuation audit, quality state, reconciliation evidence`
- `SCALING_LIMIT=valuation frequency and request/consumer transaction time`
- `FUTURE_EXTRACTION_TRIGGER=p95 breach, excessive valuation frequency, independent scheduling or autoscaling requirement`
- `STANDALONE_WORKER_REQUIRED_FOR_CURRENT_RELEASE=NO`

Certification covers stale inputs, exceptions/rollback, deterministic
recalculation, duplicate recomputation and reconciliation—not a nonexistent
worker-process kill.

## TREASURY

- `CURRENT_EXECUTION_MODEL=IN_PROCESS_SYNCHRONOUS_SIMULATION_READ_MODEL`
- `PROCESS_BOUNDARY=application treasury simulation service invocation`
- `TRANSACTION_BOUNDARY=atomic calculation/plan service operation`
- `FAILURE_BOUNDARY=calculation input, dependency timeout, PostgreSQL transaction`
- `RETRY_MODEL=recompute from authoritative application projections`
- `IDEMPOTENCY_MODEL=tenant-scoped plan idempotency key and source reference uniqueness`
- `RECONCILIATION_MODEL=simulation-only aggregation and persisted evidence checks`
- `OBSERVABILITY=treasury audit and simulation-tagged outbox events`
- `SCALING_LIMIT=calculation duration and database contention`
- `FUTURE_EXTRACTION_TRIGGER=independent retry lifecycle, isolation, scheduling or autoscaling requirement`
- `STANDALONE_WORKER_REQUIRED_FOR_CURRENT_RELEASE=NO`

Treasury produces no real transfers. Failure certification targets rollback,
duplicate calculation, recomputation and invariant checks.

## REGULATORY_RECORDS

- `CURRENT_EXECUTION_MODEL=IN_PROCESS_SYNCHRONOUS_EVIDENCE_AUTHORITY`
- `PROCESS_BOUNDARY=application audit/compliance/surveillance evidence service invocation`
- `TRANSACTION_BOUNDARY=business mutation transaction and append-only evidence write`
- `FAILURE_BOUNDARY=evidence transaction, hash validation and PostgreSQL`
- `RETRY_MODEL=replay idempotent event/request and reconcile evidence linkage`
- `IDEMPOTENCY_MODEL=provider/event identity, append-only audit and evidence hashes`
- `RECONCILIATION_MODEL=compliance/surveillance reconciliation and audit-gap checks`
- `OBSERVABILITY=immutable audit records, evidence hashes and reconciliation metrics`
- `SCALING_LIMIT=evidence volume on the synchronous transaction path`
- `FUTURE_EXTRACTION_TRIGGER=regulatory workload affects trading latency or requires independent retention/retry/autoscaling`
- `STANDALONE_WORKER_REQUIRED_FOR_CURRENT_RELEASE=NO`

Certification covers rollback, duplicate generation, hash mismatch detection,
delayed capture and reconciliation. It does not claim a standalone regulatory
worker recovery test.
