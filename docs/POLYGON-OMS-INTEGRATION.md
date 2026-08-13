# Polygon Open Money Stack integration readiness

Reviewed against current official Polygon documentation on **2026-08-11**.

## Documented API facts

- API version: `v0.11` (the current overview and payment examples; one auth reference example still renders `v0.9`, so implementation must pin the owner-approved version).
- Sandbox base URL: `https://sandbox-api.polygon.technology/v0.11`.
- Production base URL: `https://api.polygon.technology/v0.11` (not authorized or contacted).
- Authentication: exchange an API key and one-time secret at `POST /auth/token`; use the returned bearer token for up to 60 minutes.
- Access: early access, granted on request. No account, credential, sandbox entitlement, or production entitlement was found on the authorized host.

Sources: [OMS overview](https://docs.polygon.technology/api-reference/overview), [authentication](https://docs.polygon.technology/api-reference/auth/get-bearer-token), and [documentation index](https://docs.polygon.technology/llms.txt).

## Capability inventory

The public reference documents customers, custodial wallets and balances,
quotes, transactions, cash-in, virtual accounts, deposit addresses, external
accounts, counterparties, webhooks, and supported-network discovery. It
describes fiat/card/cash and crypto routes, but actual rails, assets, networks,
compliance endorsements, and products are project configuration and entitlement
dependent. They are therefore `DOCUMENTED_NOT_ENTITLED`, not enabled features.

Cross-chain is described at the platform level but is not activated here.
`CROSS_CHAIN_TRANSFERS_ENABLED=false` is mandatory.

## Runtime posture

`provider_id=polygon_oms`, type `FINANCIAL_INFRASTRUCTURE`, state `DISABLED`.
No provider credential is stored, no network client exists, and the application
cannot issue an OMS mutation. Fixture identifiers contain no real PII.

The authorized integration profile is `CUSTODIAL`. OMS—not the Beyvra
application backend or frontend—retains and manages wallet keys. This readiness
decision does not activate custody, a provider, production, or real money.

## Public API

No Polygon-specific public schema or route is introduced. Beyvra clients remain
on provider-neutral wallet, deposit, withdrawal, transfer, and compliance APIs.
All real routes remain `FEATURE_DISABLED`.
