# Email OTP registration

Password registration now uses `POST /api/v1/auth/register`, followed by
`POST /api/v1/auth/email-verification/verify` and the neutral resend/status
routes. Pending registrations and challenges are PostgreSQL-backed. OTPs use
PBKDF2-HMAC with a server-side pepper, expire after 600 seconds, allow five
attempts, and invalidate older challenges on resend. Raw codes are encrypted
only in the short-lived outbox payload needed by the worker and are never
returned by status endpoints or audit events.

Successful verification atomically creates an active user, records the OTP
verification source, persists legal acceptances, creates the demo wallet, and
queues one idempotent welcome-email outbox event. The existing legacy
`/api/user/create/` endpoint rejects direct account creation while OTP
verification is enabled, preventing an unverified-registration bypass.

The email worker is provider-neutral at the outbox boundary and currently
remains disabled by configuration (`TRANSACTIONAL_EMAIL_ENABLED=false` and
`WELCOME_EMAIL_ENABLED=false`) until an approved staging provider is supplied.
Google OIDC registrations with server-verified `email_verified=true` record
`google_oidc` and do not create an OTP challenge.
