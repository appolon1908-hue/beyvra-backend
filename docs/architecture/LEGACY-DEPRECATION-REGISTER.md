# Legacy Deprecation Register

| Component | Classification | Successor / disposition | Writable authority |
|---|---|---|---|
| `real_wallet` application and former `/api/v1/legacy-real-wallet/*` | FROZEN_LEGACY | `financial_boundary` canonical `/api/v1/*` money contract | none; app is not installed/routed/imported; tables preserved pending owner-led archival |
| `/api/wallet/*` | DEPRECATED_COMPATIBILITY | simulation wallet or Financial Service boundary by operation | demo-only; real value denied |
| `/api/trades/*` and `trade.Trade` | DEPRECATED_COMPATIBILITY | `/api/v1/trading/*`, canonical trading/post-trade models | compatibility only |
| `/api/payment/*` | DEPRECATED_COMPATIBILITY | Financial Service boundary | real movement denied |
| `apps.platform_api` | REMOVE_AFTER_MIGRATION_DEPENDENCY_REVIEW | `operations`, existing auth/demo modules, and Financial Service boundary | not installed or routed |
| colon-form market channels | REMOVE | dotted V2 registry | none |
| `market.compat.crypto`, `market.compat.stocks`, `compat.platform` | REMOVE | V2 channels plus REST recovery | none; frontend consumers removed |
| `application.*` subjects | REMOVE | domain-qualified event subjects | publisher rejects |

Physical model removal is deferred where historical Django migrations or explicit compatibility consumers still exist. No candidate may remove those tables until the no-consumer, no-import, no-event-consumer, and no-required-migration-dependency checks all pass.
