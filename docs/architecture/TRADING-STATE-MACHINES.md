# Canonical Trading State Machines

State changes are performed by the named service modules under database row
locks. Serializers, model admins, provider adapters, and compatibility views do
not expose direct state mutation.

## Order

```text
PENDING -> ACCEPTED | REJECTED | CANCELLED
ACCEPTED -> OPEN | REJECTED | CANCEL_PENDING | EXPIRED
OPEN -> PARTIALLY_FILLED | FILLED | CANCEL_PENDING | EXPIRED | REJECTED
PARTIALLY_FILLED -> PARTIALLY_FILLED | FILLED | CANCEL_PENDING | EXPIRED
CANCEL_PENDING -> CANCELLED
FILLED | CANCELLED | REJECTED | EXPIRED -> terminal
```

Authority: `apps.trading.domain.orders.transition_order`, persisted through the
canonical simulation application/repository services.

## Execution

```text
CREATED -> SUBMITTED -> ACKNOWLEDGED -> PARTIALLY_FILLED -> FILLED
                         |                 |
                         +-> REJECTED      +-> CANCELLED
SUBMITTED | ACKNOWLEDGED -> UNKNOWN -> RESOLVED
```

Authority: `apps.trading.execution_control.state`. Provider status is normalized
before a transition and cannot write order or trade state directly.

## Trade

```text
execution fill -> CAPTURED -> VALIDATING -> VALIDATED
-> ALLOCATION_PENDING -> ALLOCATED -> SETTLEMENT_PENDING
```

Trade capture is unique by execution and source event. Corrections append
evidence/versioned records instead of destructively editing economic fields.

## Post-trade and settlement workflow

```text
SETTLEMENT_PENDING -> SETTLEMENT_INSTRUCTED -> SETTLEMENT_PROCESSING
-> SETTLED | EXCEPTION | FAILED
SETTLEMENT_PENDING | SETTLEMENT_INSTRUCTED -> CANCELLED
```

`SETTLED` here means the simulation/workflow projection consumed an authorized
result. It does not establish real monetary finality, which belongs exclusively
to Financial Service.

```text
CONFLICTING_STATE_MACHINES=0
DIRECT_STATE_BYPASS_PATHS=0
```
