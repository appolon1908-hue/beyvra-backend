# Business-email Middleware destination policy

Business email remains disabled by default. This source change does not authorize
email delivery, deploy a service, configure DNS, or activate any financial effect.

## Independent destination and trust configuration

`BEYVRA_EMAIL_API_URL` selects the dedicated private Middleware origin.
`BEYVRA_EMAIL_ALLOWED_ORIGINS` independently lists the exact origins approved by
the infrastructure/identity owners for that environment. Its environment-variable
format is a comma-separated list; a Django setting may instead supply a sequence.
There are no default trusted origins. Never derive the allowlist from the selected
endpoint or add an origin merely to make a failed check pass.

Owners must verify private routing, DNS ownership, and service identity before
binding this configuration. Prefer HTTPS with certificate verification. Existing
HTTP transport support is retained only for an explicitly reviewed origin; an
HTTPS allowlist entry never authorizes an HTTP downgrade. Network egress controls
must separately enforce private routing; URL matching does not prove DNS routing.
The allowlist is trusted deployment policy and must not be writable by callers.

The checked-in `.env.example` keeps `TRANSACTIONAL_EMAIL_ENABLED=false` and the
endpoint empty. Before a separately approved activation, configure BOTH values
through reviewed environment configuration. No production destination is inferred
or introduced by this PR. `middleware.internal` in tests is a mocked fixture only.

## Enforcement

The client normalizes case, a single terminal DNS dot, and default ports, then
requires an exact scheme/host/port match before obtaining a service token or
attempting delivery. That canonical origin is also used for the actual request.
Wildcards, credentials, path prefixes, query/fragment components, control
characters, invalid ports, and ambiguous host spellings are rejected. The public
Kong and known direct Klyrow provider hosts remain forbidden even if allowlisted.

Missing endpoint or allowlist configuration is retryable, preserving pending
outbox intent. Malformed policy or an untrusted destination fails closed. Redirects
are never followed or reported as delivery success; malformed or non-object JSON
responses are failures. Identity mail remains Keycloak-owned when its identity
authority is enabled. Bearer tokens and message payloads are never logged.

## Validation

`notifications.test_email_destination_policy` covers destination confusion,
missing trust policy, malformed origins, known provider bypasses, transport/port
mismatches, normalization, Keycloak boundaries, redirects and response shape.
All outbound calls are mocked. Existing email integration coverage is preserved;
its allowlist fixture is explicit and the shared token cache is reset per test.

The Email boundary safety workflow runs both test modules against PostgreSQL 16
on the exact PR head. The existing CI remains unchanged. Local isolated tests are
not a substitute for that full Django/PostgreSQL run and independent review.
