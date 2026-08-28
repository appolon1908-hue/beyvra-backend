# Order Unknown Outcome Runbook

## Scope & Trigger Conditions
When an external execution venue, broker, or simulation engine transport times out or disconnects during order routing:
- The order must NEVER be automatically assumed rejected.
- The order must NEVER be blindsided with duplicate resubmissions.
- The state must be transitioned to `UNKNOWN` with `reconciliation_required = true`.

## Handling Procedure
1. **Immediate State Transition**:
   - Transition order status to `UNKNOWN`.
   - Freeze buying power reservation (do not release until authoritatively confirmed).
   - Enqueue reconciliation task in PostgreSQL durable queue.

2. **Automated Reconciliation Loop**:
   - Query execution provider status endpoint using canonical order reference and idempotency key.
   - If provider reports order as acknowledged/active -> Transition to `ACKNOWLEDGED`.
   - If provider reports order as filled -> Transition to `FILLED` or `PARTIALLY_FILLED` and process fills.
   - If provider reports order unknown / never received -> Transition to `REJECTED` and release reservation.

3. **Escalation & Operator Intervention**:
   - If automated reconciliation exceeds max retry limit (5 attempts over 5 minutes), alert on-call SRE.
   - Run manual verification via operator execution reconciliation CLI.
   - Force terminal resolution with signed operator audit trail.
