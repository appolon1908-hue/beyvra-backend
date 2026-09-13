# API registry during PAPER/LIVE migration

The runtime contract is `contracts/openapi/beyvra-openapi-3.1.yaml`, generated from
the existing Django handlers. `docs/API-IMPLEMENTATION-MATRIX.md` records discovered
operation IDs and verified implementation evidence. Its unresolved entries are
not complete features. Historical inventory counts do not describe this head.

| Classification | Surface | Migration authority |
|---|---|---|
| CANONICAL | `/api/v1/workspace/bootstrap`, `/api/v1/watchlists` | Existing tenant/user-scoped workspace services |
| CANONICAL | `/api/v1/news`, `/api/v1/economic-calendar`, `/api/v1/instruments` | Existing normalized customer services, extended in B04/B05 |
| COMPATIBILITY | `/api/v1/trading/*` | Extend existing trading services behind account-selected `/api/v1/orders`, `/executions`, `/positions` in B06/B12 |
| COMPATIBILITY | `/api/v1/market/*` | Migrate callers to `/api/v1/market-data/*` in B04/F02/F03 |
| COMPATIBILITY | `/api/v1/realtime/v2/*` | Extend token/session authority under `/api/v1/realtime/session` in B17; one `/ws/v2` transport |
| COMPATIBILITY | `/api/v1/operator/*`, `/api/v1/admin/*`, legacy `/api/admin/*` | Migrate existing workforce handlers to `/api/admin/v1/*` in B13 |
| DEPRECATED | `/api/user/*`, `/api/trades/*`, `/api/wallet/*`, `/api/payment/*` | Preserve fail-closed boundaries until callers migrate; no new implementation here |
| REMOVE | `/api/v1/demo/*` and guest-session creation aliases | Retired in B00; regression tests reject their return |
| CANONICAL | `/health/*`, `/metrics`, `/api/schema/*` | Infrastructure only; no business-state mutation |

Classification is a migration policy, not a claim that a target handler or adapter
already exists. User-approved production rollout still requires all milestone,
provider, ledger, risk, compliance, reconciliation and staging evidence. Financial
capabilities remain subject to certification and explicit activation gates.
