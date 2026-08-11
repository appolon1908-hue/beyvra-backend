# Financial Service contract

API version is `v1`; supported versions: `v1`. Breaking field, type, required-property, enum, or endpoint changes require a new version and consumer contract approval.

The private client supplies mTLS certificate/key, CA verification, `X-Service-Scope: financial.application`, `X-Service-Audience: financial-service`, tenant, subject, request and correlation context. Connect timeout is 2 seconds, request timeout 5 seconds, and safe-read retries default to 2. Mutations are never automatically retried. A connection loss or timeout during mutation is `UNKNOWN_OUTCOME`; canonical lookup by reference/idempotency key must precede any subsequent mutation.

Live v1 supports health/readiness, wallet list/detail/balances, deposit and withdrawal reads, disabled withdrawal/transfer mutations, ledger-transaction read, disabled holds, and reconciliation run stubs. Reservation/release semantics, settlement, deposit intent, operation lookup, and asset-keyed wallet snapshots are absent as of the recorded Financial Service head. Client methods for those operations fail locally with `CONTRACT_UNAVAILABLE`; owner-approved Financial Service versioning is required before certification. Amounts are finite non-negative decimal strings plus uppercase asset code and precision. Floating point, NaN, Infinity, negatives, and excessive precision are rejected.

Errors map to safe application categories: `VALIDATION_ERROR`, `INSUFFICIENT_FUNDS`, `IDEMPOTENCY_CONFLICT`, `RESTRICTION`, `NOT_FOUND`, `TRANSIENT_UNAVAILABLE`, and `UNKNOWN_OUTCOME`. Internal hostnames, mTLS details, provider errors and request identifiers are not returned.
