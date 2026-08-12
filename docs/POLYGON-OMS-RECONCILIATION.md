# Polygon OMS reconciliation proposal

Financial Service should reconcile the immutable chain:

```text
Beyvra intent -> Financial operation -> OMS transaction -> wallet projection
              -> deposit/withdrawal/transfer -> inbox/outbox -> audit
```

Detect missing OMS operations, duplicate effects, provider-state mismatches,
wallet projection mismatches, stuck pending operations, unknown outcomes, stale
or gapped webhook sequences, and audit gaps. Provider balance is evidence, not
Beyvra's ledger authority.

Reconciliation is read-only. It may emit an alert, incident, and activation-gate
failure. It must never repair a ledger, replay a money movement, or mark an
unknown state settled. Following a timeout after mutation, lookup the operation
by stable idempotency/operation reference before considering a retry.

An isolated restore must include entity/wallet mappings, operations,
idempotency records, inbox, outbox, webhook sequence cursors, provenance, audit,
and reconciliation runs. After restore, run read-only reconciliation before any
adapter can leave `DISABLED`.
