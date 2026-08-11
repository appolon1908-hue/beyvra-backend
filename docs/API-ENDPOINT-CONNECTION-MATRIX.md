# API endpoint connection matrix

This matrix records the meaningful browser → application → Financial Service boundaries. The complete application OpenAPI remains available at `GET /api/schema/`; the tables below cover every provider-neutral financial, market, trading, notification, webhook, and realtime URL used by the current frontend.

## Public financial API

| Method and URL | Purpose | Current response/authority | Frontend caller |
|---|---|---|---|
| `GET /api/v1/features/` | Authoritative server feature discovery | All real-value flags remain false | `financialApi.features` |
| `GET /api/v1/wallets/` | Wallet snapshot collection | `FEATURE_DISABLED` while real reads are off | `financialApi.wallets` |
| `GET /api/v1/wallets/{asset}/` | Asset wallet snapshot | `FEATURE_DISABLED` while real reads are off; asset path resolves rather than returning route-level 404 | `financialApi.wallet` |
| `GET, POST /api/v1/deposits/` | Deposit history / future intent | Reads and writes fail closed under current flags | `financialApi.deposits`, `createDeposit` |
| `GET /api/v1/deposits/{id}/` | Deposit detail | Fail-closed detail contract | `financialApi.deposit` |
| `GET, POST /api/v1/withdrawals/` | Withdrawal history / future intent | Writes return `FEATURE_DISABLED` before any Financial Service/provider call | `financialApi.withdrawals`, `createWithdrawal` |
| `POST /api/v1/withdrawals/preview/` | Non-mutating eligibility/fee preview | Disabled until an authoritative preview contract is enabled | `financialApi.previewWithdrawal` |
| `GET /api/v1/withdrawals/{id}/` | Withdrawal detail | Fail-closed detail contract | `financialApi.withdrawal` |
| `POST /api/v1/withdrawals/{id}/cancel/` | Cancel before irreversible submission | Disabled; no provider call | `financialApi.cancelWithdrawal` |
| `GET, POST /api/v1/transfers/` | Transfer history / future intent | Disabled; no financial effect | `financialApi.transfers`, `createTransfer` |
| `GET /api/v1/transfers/{id}/` | Transfer detail | Fail-closed detail contract | `financialApi.transfer` |
| `POST /api/v1/transfers/preview/` | Non-mutating transfer preview | Disabled | `financialApi.previewTransfer` |
| `GET /api/v1/compliance/profile/` | Canonical eligibility profile | Disabled until compliance authority is connected | `financialApi.complianceProfile` |
| `GET /api/v1/compliance/requirements/` | Canonical requirement list | Disabled until compliance authority is connected | `financialApi.complianceRequirements` |

Trailing slashes are canonical for these Django application endpoints. This avoids unsafe POST redirects. The frontend registry now uses the same canonical forms.

## Financial Service internal API

These routes are server-to-server only and are never called by the browser.

| Method and URL | Purpose |
|---|---|
| `GET /internal/v1/health/live` | Process liveness |
| `GET /internal/v1/health/ready` | Database/service readiness |
| `GET /internal/v1/metrics` | Internal Prometheus metrics |
| `GET /internal/v1/wallets[/{wallet_id}]` | Authoritative wallet lookup, feature-gated |
| `GET /internal/v1/wallets/{wallet_id}/balances` | Authoritative balance lookup, feature-gated |
| `GET /internal/v1/deposits[/{deposit_id}]` | Deposit lookup |
| `GET, POST /internal/v1/withdrawals[/{withdrawal_id}]` | Withdrawal lookup/fail-closed mutation |
| `POST /internal/v1/withdrawals/preview` | Future non-mutating preview |
| `GET, POST /internal/v1/transfers` and `POST /internal/v1/transfers/preview` | Transfer lookup/fail-closed mutation |
| `GET /internal/v1/provider-operations[/{reference}]` | Unknown-outcome/idempotency recovery lookup |
| `POST /internal/v1/providers/polygon-oms/webhooks` | Verified OMS provider webhook ingress |

## Realtime and webhooks

| URL | Purpose | Ownership |
|---|---|---|
| `POST /api/v1/realtime/v2/connection-token` | Short-lived private gateway token | Application backend |
| `POST /api/v1/realtime/v2/subscription-token` | Channel-scoped subscription token | Application backend |
| `WS /ws/v2/` | Canonical browser realtime gateway | Application backend; frontend uses this exact path |
| `WS /ws/v1/` | Measured compatibility alias | Same canonical consumer; retire after legacy usage reaches zero |
| `POST /internal/v1/providers/polygon-oms/webhooks` | OMS state events | Financial Service only; never public browser API |
| `/api/v1/notifications/webhooks/` | Customer notification webhook subscription management | Application backend; unrelated to OMS ingress |

## Market and trading API

Canonical frontend market calls use `/api/v1/market/*`; simulation order calls use `/api/v1/trading/*`. Order-book and trade-stream snapshots explicitly return `CAPABILITY_UNSUPPORTED` when no genuine provider capability exists. They never reuse a market-status payload or synthesize data.

Legacy `/api/trades/*`, `/api/wallet/*`, `/api/payment/*`, `/api/notification/*`, and `/ws/v1/` URLs are compatibility surfaces, not duplicate authorities. New frontend financial and realtime code must use `/api/v1/*` and `/ws/v2/`. Compatibility usage is measured and should be removed only through a separately reviewed retirement change.

## Connection invariants

- Browser provider URLs and direct Financial Service URLs: zero.
- Application direct OMS calls and Financial PostgreSQL access: zero.
- Public paths resolve to application handlers; internal paths resolve only inside Financial Service.
- Disabled operations return a stable application error rather than route-level 404/405 or provider diagnostics.
- `apps.foundation.test_endpoint_connections` prevents canonical frontend paths from becoming unbound or semantically miswired.
