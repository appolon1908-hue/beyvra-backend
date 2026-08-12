# API Security Certification

## Enforced controls

- JWT authentication protects customer and operator resources. Password recovery is enumeration-safe; logout validates token ownership and records server-side revocation state.
- Tenant/resource queries bind organization and subject before lookup. Cross-tenant identifiers return `NOT_FOUND`.
- Operator access uses scoped membership roles. Sensitive action approval rejects the maker and appends immutable audit evidence.
- Cookie-authenticated browser mutations retain Django CSRF protection; JWT routes do not disable CSRF globally. Authenticated CORS is allowlisted and wildcard origins remain disabled.
- `Idempotency-Key` and PostgreSQL uniqueness serialize duplicate support, report, privacy, operator, demo, and simulated-order submissions.
- Webhooks authenticate before parsing or mutation, bound bodies, reject stale/future signatures, detect payload conflicts, and dead-letter unknown types.
- Public errors omit request/correlation IDs, internal paths, service names, SQL, exceptions, and stack traces. Correlation IDs remain internal and are no longer echoed as response headers.
- Financial values use Decimal/string representations; timestamps are timezone-aware UTC.
- Real wallet reads, deposits, withdrawals, transfers, trading, external execution, and real money are compile-time false in Django settings. Legacy payment/provider mutations also check these authorities before provider code.

## Evidence

The PostgreSQL tests include anonymous, wrong-tenant, IDOR, least-privilege, maker/checker, idempotency conflict/replay, 16-way concurrent duplicate submission, 100 webhook duplicate deliveries, invalid/missing/stale/future signatures, malformed/oversized bodies, safe errors, and fail-closed real-value probes. Counts and commands are recorded under `docs/evidence/api-certification/`.

No Financial PostgreSQL configuration exists in `DATABASES`; application Financial Service access remains an mTLS HTTP client contract only.
