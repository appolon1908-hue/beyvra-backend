# Security and Authentication Readiness

## Controls verified

- JWT refresh ownership and logout blacklisting; password reset revokes outstanding tokens.
- MFA password login issues no access/refresh token before a valid five-minute challenge.
- TLS redirect, Secure, HttpOnly and SameSite=Lax cookie settings; HSTS in non-debug deployments.
- Default authentication/authorization, self-or-staff user detail boundary, and simulation authority gate.
- Anonymous/user plus scoped throttling for login, reset, MFA, order preview/create and guest demo.
- Generic trading errors omit request/correlation IDs, raw exceptions, paths and service names.
- Application has no Financial PostgreSQL alias or credentials; NATS/bridge use scoped TLS files.
- Admin routes retain Django staff authorization and existing audit controls.

## Changes

Enabled `ScopedRateThrottle`, assigned bounded scopes, closed cross-user detail access,
and removed internal request identifiers from trading errors. Fifty-eight isolated
security/trading/reconciliation tests pass on PostgreSQL 16.

## Frontend token-storage review

The frontend stores no access or refresh tokens in `localStorage` or
`sessionStorage`. It currently stores bearer tokens in cookies readable by JavaScript
because the SPA reads them to construct Authorization headers. All token-writing paths
were standardized to `Secure`, `SameSite=Strict` and `Path=/`; persistent login keeps
the existing 30.4-day maximum age. This does not protect a bearer token from successful
same-origin script execution.

Before real-money readiness, migrate to backend-issued `HttpOnly`, `Secure`,
`SameSite=Strict` session/refresh cookies, keep short-lived access material in memory
or behind a same-origin BFF, add CSRF protection for cookie-authenticated mutations,
and remove direct token access from React. This coordinated migration is not
represented as complete by the cookie-option hardening.

## Deferred external evidence

Credential rotation/revocation and independent security approval remain owner actions.
No such evidence is claimed. The HttpOnly/BFF migration above remains an architecture
action before real-money readiness.
