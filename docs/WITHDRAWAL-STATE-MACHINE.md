# Withdrawal state machine

`CREATED → PENDING_VALIDATION → PENDING_COMPLIANCE → PENDING_APPROVAL → APPROVED → QUEUED → SUBMITTED → PENDING_CONFIRMATION → COMPLETED`. Terminal alternatives are `REJECTED`, `CANCELLED`, `FAILED`; only completed may become `REVERSED`. Cancellation is allowed through `QUEUED`, never after `SUBMITTED`. Row/operation serialization must select exactly one result in cancel-versus-submit races.

Request fields: `account_ref`, `asset`, decimal-string `amount`, `destination_ref`, `beneficiary_ref`, and idempotency key. Raw keys and raw provider credentials are forbidden.
