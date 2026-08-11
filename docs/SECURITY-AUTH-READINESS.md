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

## Deferred external evidence

Credential rotation/revocation and independent security approval remain owner actions.
No such evidence is claimed. Browser token-storage policy requires frontend review in
its own repository; this backend work does not assert that local storage is unused.
