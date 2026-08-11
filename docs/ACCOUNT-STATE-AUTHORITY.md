# Account state authority

`ComplianceProfile.account_state` is the canonical auditable state: `PENDING`, `ACTIVE`, `RESTRICTED`, `SUSPENDED`, or `CLOSED`. Eligibility uses this value under row-locked mutation workflows; legacy booleans are not authority. New profiles default to `PENDING`. Each mutation must emit an immutable audit event and transactional outbox event. Closed/suspended/restricted/pending accounts fail closed.
