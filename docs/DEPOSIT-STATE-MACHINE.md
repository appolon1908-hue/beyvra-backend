# Deposit state machine

`CREATED → AWAITING_FUNDING → DETECTED → PENDING_CONFIRMATION → COMPLIANCE_REVIEW → CREDIT_PENDING → CREDITED`, with explicit `FAILED`/`CANCELLED` exits and `CREDITED → REVERSED`. Transitions may skip compliance review only when authoritative policy permits. A boolean success is forbidden.

Events: `financial.deposit.created.v1`, `.detected.v1`, `.pending.v1`, `.credited.v1`, `.failed.v1`, `.reversed.v1`. Confirmation and reorg data must originate from an approved authority. `POST /api/v1/deposits/` returns `FEATURE_DISABLED` and creates neither address nor intent.
