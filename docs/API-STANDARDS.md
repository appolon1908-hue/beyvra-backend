# Beyvra API Standards

## Authority and versioning

Public contracts use `/api/v1/*`. Realtime uses `/ws/v2/`. Compatibility routes may remain only as delegates to an existing domain service and must carry documented deprecation ownership. Provider objects and database models are not public schemas.

## Authentication, authorization, and tenancy

Public customer resources require JWT authentication except login, password recovery, safe status/features, and authenticated provider webhooks. Every resource query is scoped by both organization and subject. A foreign identifier returns the same `NOT_FOUND` shape as an absent identifier. Operator access requires an explicit organization membership role; generic `is_staff` is not an operator authority. Sensitive operator actions use independent maker/checker approval.

## Mutations and idempotency

Potentially duplicative mutations require `Idempotency-Key` (1–255 characters). The authority stores tenant, subject, scope, key, canonical request hash, response, and expiry. Same key/body replays the logical result; a changed body returns `409 IDEMPOTENCY_CONFLICT`. Domain state, audit/outbox records, and the idempotency result commit atomically.

## Pagination, filtering, and ordering

Canonical lists use `{results, next}` with `limit` from 1 through 100 and an opaque cursor. Rapidly changing data is ordered deterministically by descending unique identifier. Supported bounded filters are `created_after`, `created_before`, `status`, `instrument`, and `asset`; unsupported or invalid values return `VALIDATION_ERROR`.

## Money and time

Money, price, fee, and quantity values are validated and represented with `Decimal`-safe strings. Binary floating point is not a financial authority. Internal timestamps are timezone-aware UTC and public timestamps are RFC 3339.

## Errors

Errors use `{error: {code, message, fields?}}`. Stable categories include `VALIDATION_ERROR`, `AUTHENTICATION_REQUIRED`, `PERMISSION_DENIED`, `NOT_FOUND`, `CONFLICT`, `IDEMPOTENCY_CONFLICT`, `FEATURE_DISABLED`, `RATE_LIMITED`, `PROVIDER_NOT_AVAILABLE`, `TEMPORARILY_UNAVAILABLE`, and `INTERNAL_ERROR`. Public bodies and headers omit request/correlation IDs, stack traces, SQL, internal hosts, provider details, and raw exception text.

## Audit, outbox, and rate limiting

Sensitive mutations append an immutable, tenant-scoped audit event. Mutations with downstream consequences append a transactional outbox event. Login, password recovery, MFA, trading, exports, support, privacy, integrations, and operator routes use bounded throttles. Metrics use route templates and bounded outcome labels; they never label user or resource identifiers.

## Deprecation

Compatibility endpoints are classified `KEEP_COMPATIBILITY`, `MIGRATE`, `DEPRECATE`, or `REMOVE_LATER`. Deprecating responses use `Deprecation`, `Sunset`, and `Link: <successor>; rel="successor-version"`; removal requires measured zero usage and owner approval.
