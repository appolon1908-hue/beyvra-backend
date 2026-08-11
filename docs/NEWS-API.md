# Canonical news API

Authenticated endpoints:

- `GET /api/v1/news` — Latest
- `GET /api/v1/news/{news_id}` — canonical stored article
- `GET /api/v1/news/crypto`
- `GET /api/v1/news/market`
- `GET /api/v1/news/sources`
- `GET /api/v1/news/archive` — only when entitled

Collections return `{results, next_cursor, delayed, stale}`. Articles expose canonical fields only. Safe errors are `PROVIDER_NOT_AVAILABLE`, `CAPABILITY_NOT_AVAILABLE`, `VALIDATION_FAILED`, and `NOT_FOUND`. Provider URLs, exceptions, raw payloads, request IDs, quota metadata, pagination tokens and credentials are not exposed.

