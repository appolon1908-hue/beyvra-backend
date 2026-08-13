# Institutional account inventory

Reviewed at backend head `1289857` on 2026-08-11.

| Existing component | Classification | Decision |
|---|---|---|
| `integrations.Organization` and membership | PARTIAL | Tenant boundary reused; it is not an institutional account. |
| `integrations.DemoAccount` | LEGACY for this domain | Remains isolated practice state. |
| `wallet.Wallet`, demo trades and positions | CUSTOMER_UI_ONLY | Never treated as custody, ownership, or clearing evidence. |
| `real_wallet` custody adapters | PROVIDER_SPECIFIC / DISABLED | No live adapter is activated. |
| clearing-named demo ledger accounts | LEGACY | Accounting labels only, not clearing relationships. |
| compliance profile and opaque evidence refs | AUTHORITATIVE for compliance only | Ownership stores opaque references, never copied KYC records. |
| Financial Service client | AUTHORITATIVE boundary | Application does not access Financial PostgreSQL or create a shadow cash ledger. |
| institutional hierarchy, ownership, custody, allocation, clearing and settlement mapping | MISSING | Implemented by `apps.institutional`. |

Search covered institution, tenant, master/subaccount, beneficial owner,
custody, omnibus, segregation, clearing, broker mapping, allocation, portfolio,
house/client account, and settlement terminology across models, routes,
migrations, provider adapters, and frontend-facing contracts.
