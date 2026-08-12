# API inventory

Static extraction found 318 backend route declarations across HTTP and WebSocket URL configurations.

## Top-level families

| Prefix | Classification |
|---|---|
| `/api/v1/auth/*` | canonical authentication |
| `/api/v1/demo/*` | canonical simulation |
| `/api/v1/trading/*` | intended canonical trading; several resources are placeholders |
| `/api/v1/market/*`, `/api/v1/market-data/*` | conflicting market route families |
| `/api/v1/realtime/v2/*` | canonical realtime control plane |
| `/api/v1/*` real-wallet routes | noncanonical dormant shadow financial implementation |
| `/api/user/*`, `/api/wallet/*`, `/api/payment/*`, `/api/trades/*` | legacy/compatibility APIs |
| `/api/admin/*` | legacy operator APIs requiring separate RBAC/IDOR review |
| `/api/orders/*` Alpaca routes | legacy direct-provider surface; noncanonical |

Known duplicates include slash/no-slash integration aliases, `deposit`/`deposite`, two demo-order registrations, two market route modules, and duplicate YAML path keys for real-wallet deposits and withdrawals.

Detailed method/auth/serializer/OpenAPI/frontend-consumer status remains tracked in the conflict and missing-implementation registers because static URL declarations alone cannot prove runtime methods or authorization.
