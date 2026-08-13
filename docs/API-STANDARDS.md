# API standards

Canonical HTTP APIs use `/api/v1/*`; realtime uses `/ws/v2/`. Contracts require authentication, authorization, tenant/account isolation, bounded pagination, validation, canonical safe errors, rate limits, audit, and idempotency on mutations.

Provider names, URLs, credentials, exceptions, raw responses, stack traces, and internal request identifiers are not public contract fields. Unsupported authoritative capability returns `CAPABILITY_UNSUPPORTED`; unavailable authority returns `PROVIDER_NOT_AVAILABLE`; disabled real-value actions return `FEATURE_DISABLED`.

OpenAPI is generated and drift-checked in CI. Route tests cover success, auth, authorization/isolation, validation, not found, conflict, disabled capability, and safe failure as applicable.

