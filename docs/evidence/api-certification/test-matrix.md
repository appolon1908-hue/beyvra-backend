# API certification test matrix

Certification date: 2026-08-11. Runtime: Python 3.11, Django, PostgreSQL 16, Redis 7.

| Control | Evidence | Result |
|---|---|---|
| Full backend regression | 237 Django tests | PASS |
| Canonical route matrix | auth, contract, safe-error and fail-closed checks | PASS |
| Tenant and object isolation | cross-organization resources resolve as not found/denied | PASS |
| Role authorization | user/operator and maker/checker coverage | PASS |
| API idempotency | replay and conflicting-payload tests | PASS |
| API concurrency | 16 simultaneous support submissions produce one effect | PASS |
| Realtime v2 | envelope, authentication, duplicate suppression and gap recovery | PASS |
| Financial boundary | wallet/deposit/withdrawal/transfer/trading disabled tests | PASS |

The route inventory is the exhaustive route-level coverage index. Sensitive route families have explicit tests; structurally identical read-only routes share the authenticated contract matrix.
