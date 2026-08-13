# Canonical API registry

The authoritative machine-readable registry is
`contracts/openapi/beyvra-v1.yaml`, generated from the integrated Django
runtime and validated with duplicate-key rejection.

| Classification | Prefix | Authority | Auth / scope | Frontend use |
|---|---|---|---|---|
| CANONICAL | `/api/v1/trading/` | trading application services | authenticated; tenant/account scoped | yes |
| CANONICAL | `/api/v1/execution/` | execution projections | authenticated; tenant/account scoped | yes |
| CANONICAL | `/api/v1/post-trade/` | post-trade workflow | authenticated; tenant/account scoped | yes |
| CANONICAL | `/api/v1/valuation/` | valuation read model | authenticated; tenant/account scoped | yes |
| CANONICAL | `/api/v1/realtime/v2/` | realtime authorization/registry | authenticated; server-derived scope | yes |
| CANONICAL | `/api/v1/wallets/`, `/deposits/`, `/withdrawals/`, `/transfers/` | Financial Service client boundary | authenticated; tenant/account scoped; fail closed | yes |
| OPERATOR | `/api/v1/operator/` | domain operator services | operator RBAC; tenant scoped | no |
| INTERNAL | `/api/internal/v1/` | internal operations | service/operator controls | no |
| DEPRECATED_COMPATIBILITY | `/api/user/`, `/api/trades/` | read/fail-closed adapters | authenticated | migrating |
| REMOVE | `/api/wallet/`, `/api/payment/`, `/api/v1/demo/wallet`, `/api/v1/demo/trades` | none | unavailable (404) | no |

Each OpenAPI operation records method, path, view-derived operation id,
authentication and schema. Service ownership, RBAC, tenancy and consumer
classification are governed by this table plus the canonical authority map.

```text
OPENAPI_PATHS=535
OPENAPI_OPERATIONS=654
LEGACY_PATHS=156
DUPLICATE_METHOD_PATH_PAIRS=0
DUPLICATE_WRITABLE_API_AUTHORITIES=0
```
