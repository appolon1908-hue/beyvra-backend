# KYC state machine

States: `NOT_STARTED`, `PENDING`, `IN_REVIEW`, `APPROVED`, `REJECTED`, `EXPIRED`, `REQUIRES_UPDATE`.

| From | Allowed to |
|---|---|
| NOT_STARTED | PENDING |
| PENDING | IN_REVIEW, REJECTED |
| IN_REVIEW | APPROVED, REJECTED, REQUIRES_UPDATE |
| APPROVED | EXPIRED, REQUIRES_UPDATE |
| REJECTED | PENDING |
| EXPIRED | PENDING, REQUIRES_UPDATE |
| REQUIRES_UPDATE | PENDING, IN_REVIEW |

Approval requires a non-PII opaque evidence reference. Expiry and due review fail closed. Provider/manual evidence must be approved; no synthetic approval is permitted outside fixture tests.
