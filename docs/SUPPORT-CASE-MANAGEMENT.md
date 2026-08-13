# Support case management

Customer routes under `/api/v1/support/cases` are account- and tenant-scoped. A case has a canonical category, priority, state, safe summary, assignment, and timestamps. Its timeline is append-only. Customer responses use `CUSTOMER_VISIBLE_MESSAGE`; employee investigation uses `INTERNAL_NOTE`, which is excluded from customer serialization by construction.

Escalations target SECURITY, COMPLIANCE, FINANCIAL, ENGINEERING, or OPERATIONS and create an audit event. Low-risk support actions are limited to verification-email resend, session revocation, password-reset initiation, notes, and escalation. Impersonation is disabled.
