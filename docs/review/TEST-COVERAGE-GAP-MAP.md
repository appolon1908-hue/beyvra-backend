# Test coverage gap map

| Domain | Existing evidence | Gap |
|---|---|---|
| Financial boundary | backend boundary tests and Financial Service contract/integration tests | combined mTLS/RLS event flow not certified in one environment |
| Demo wallet | deposit/withdraw security tests | negative and concurrent transfer tests missing |
| Orders | canonical idempotency/security tests | cancel/replace/fill race coverage lives on unmerged branches |
| Tenant isolation | focused tests in several apps | no inventory proving every route, worker and WebSocket path |
| RBAC | MFA/security and mission tests | legacy admin endpoints lack a consolidated permission matrix |
| Realtime | V2 contract/security tests | exact public proxy path and frontend compatibility-channel parity missing |
| OpenAPI | schemas and selective tests | duplicate YAML keys and implementation drift prevent certification |
| PostgreSQL migrations | CI PostgreSQL 16 checks | migration-from-zero/reapply across all mission branches not possible until integration |
| Frontend | unit/contract/realtime scripts exist | checked-out client targets endpoints available only on unmerged backend branches |

Tests that exercise only legacy wallet/trade routes do not certify canonical order, execution, post-trade, valuation, or Financial Service authority.
