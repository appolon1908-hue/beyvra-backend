# Canonical Order Lifecycle Specification

## Overview
The canonical Order Management System (OMS) enforces a deterministic, event-driven state machine. All views, tasks, and reconciliation workers delegate to this single state authority.

## Canonical States
- `DRAFT`: Order creation intent initialized with client parameters.
- `PREVIEWED`: Pre-trade risk and quote locking completed.
- `PENDING_SUBMIT`: Idempotent submission initiated and locked.
- `ACKNOWLEDGED`: Order accepted by execution engine / simulated matching.
- `OPEN`: Order working in the market.
- `PARTIALLY_FILLED`: Order partially executed; remaining quantity working.
- `FILLED`: Terminal state; all quantity executed.
- `CANCEL_PENDING`: Cancellation requested, awaiting confirmation.
- `CANCELED` / `CANCELLED`: Terminal state; unexecuted quantity cancelled and reservation released.
- `REJECTED`: Terminal state; failed pre-trade risk, compliance, or validation checks.
- `EXPIRED`: Terminal state; time-in-force or session expiration reached.
- `UNKNOWN`: Provider timeout or uncertain transport status.
- `RECONCILIATION_REQUIRED`: Out-of-band resolution required before transitioning state.

## State Transition Rules

```
DRAFT -> PREVIEWED, REJECTED
PREVIEWED -> PENDING_SUBMIT, REJECTED, EXPIRED
PENDING_SUBMIT -> ACKNOWLEDGED, ACCEPTED, REJECTED, UNKNOWN
ACKNOWLEDGED -> OPEN, PARTIALLY_FILLED, FILLED, CANCEL_PENDING, EXPIRED
OPEN -> PARTIALLY_FILLED, FILLED, CANCEL_PENDING, EXPIRED
PARTIALLY_FILLED -> PARTIALLY_FILLED, FILLED, CANCEL_PENDING
CANCEL_PENDING -> CANCELED, CANCELLED
UNKNOWN -> RECONCILIATION_REQUIRED, ACKNOWLEDGED, REJECTED, FILLED, CANCELED
RECONCILIATION_REQUIRED -> ACKNOWLEDGED, REJECTED, FILLED, CANCELED
```

## Atomic Execution Steps
1. Lock preview record.
2. Validate tenant and account ownership.
3. Validate quote freshness (reject if quote age > 1500ms).
4. Run compliance and risk policy checks.
5. Lock account balance row and reserve buying power.
6. Create order in `PENDING_SUBMIT`.
7. Append immutable event to order audit log.
8. Persist transactional outbox event.
9. Store idempotent response.
10. Commit transaction before async dispatch.
