# API consolidation inventory

Snapshot: P0 consolidation candidate. This inventory classifies every URL family; generated members inherit the family classification. No route is removed in P0.

The Django resolver snapshot contains 594 concrete HTTP patterns: 111
canonical, 28 compatibility, 76 deprecated, 11 remove-after-migration, 365
admin-generated, two test-only, and one internal pattern. The application ASGI
inventory contains 13 legacy/internal WebSocket patterns, while the canonical
customer `/ws/v2/` gateway is provided by the existing external Centrifugo
edge: two compatibility or internal v1 paths, eight deprecated/internal public
paths, and three client-user-ID paths marked remove-after-migration. Django admin-generated
members are counted individually; the tables below are the maintainable
authoritative family classification for those concrete members.

## Classification policy

| Classification | Meaning |
|---|---|
| `CANONICAL` | Supported customer contract under `/api/v1/` or `/ws/v2/`. |
| `COMPATIBILITY` | Retained wrapper/legacy surface; must converge on canonical application services. |
| `DEPRECATED` | Compatibility surface with deprecation headers and usage metrics. |
| `INTERNAL` | Service-to-service, schema, metrics, or operational surface. |
| `ADMIN` | Staff/RBAC-controlled administration. |
| `TEST_ONLY` | Must not resolve in production URL configuration. |
| `REMOVE_AFTER_MIGRATION` | Known unsafe/duplicative route retained only while callers migrate. |

## Authoritative route-family inventory

| Route family | Classification | Successor / constraint |
|---|---|---|
| `/health/live`, `/health/ready` | INTERNAL | Process and dependency probes. |
| `/metrics` | INTERNAL | Prometheus only. |
| `/api/schema/`, `/api/frontendadmin/90210/` | INTERNAL | OpenAPI/schema tooling. |
| `/admin/**` | ADMIN | Every Django-generated admin model route inherits `ADMIN`. |
| `/api/v1/auth/providers`, `/register`, `/email-verification/**`, `/google/**` | CANONICAL | `/api/v1/auth/`. Providers remain disabled unless independently approved. |
| `/api/v1/auth/test/otp` | TEST_ONLY | Staging only; absent when `API_ENV=production`. |
| `/api/v1/session`, `/api/v1/workspace/bootstrap` | CANONICAL | Session/workspace bootstrap. |
| `/api/v1/demo/sessions`, `/orders`, `/trades`, `/config`, `/wallet`, `/wallet/refill` | CANONICAL | Demo authority only; never real money. |
| `/api/v1/realtime/v2/**` | CANONICAL | Authorization/registry for the single `/ws/v2/` connection. |
| `/api/v1/market-data/snapshot`, `/candles`, `/status` | COMPATIBILITY | Successor: `/api/v1/market/**`. |
| `/api/v1/instruments/**` | CANONICAL | Instrument metadata/rules/capabilities. |
| `/api/v1/market/instruments[/<symbol>]` | CANONICAL | Normalized market authority. |
| `/api/v1/market/quotes`, `/candles`, `/status/<symbol>`, `/orderbook/<symbol>`, `/trades/<symbol>`, `/feed-health` | CANONICAL | Provider-neutral; unsupported capabilities fail closed. |
| `/api/v1/trading/orders[/preview][/<order_id>[/cancel]]` | CANONICAL | Real mutations return `FEATURE_DISABLED`. |
| `/api/v1/trading/trades[/<trade_id>]`, `/positions[/<position_id>]`, `/accounts[/<account_id>]`, `/fees` | CANONICAL | Spot foundation; no leverage/margin. |
| `/api/v1/news[/<article_id>]`, `/api/v1/economic-calendar` | CANONICAL | Governance-first; unavailable providers return 503 with zero outbound calls. |
| `/api/v1/status/`, `/features/` | CANONICAL | Real-wallet capability state only. |
| `/api/v1/assets/`, `/networks/`, `/asset-networks/` | CANONICAL | Read-only reference data. |
| `/api/v1/wallets/**`, `/deposits/**`, `/withdrawals/**`, `/transfers/**` | CANONICAL | Financial Service authority; mutations disabled. |
| `/api/v1/wallet-statements/**`, `/compliance/**`, `/beneficiaries/`, `/api-keys/` | CANONICAL | Disabled until independent services/policies are approved. |
| `/api/v1/notifications/`, `/reports/` | CANONICAL | Disabled real-value boundary; legacy notification/reporting routes remain below. |
| `/api/v1/webhook-subscriptions/**`, `/integrations/webhooks/**` | INTERNAL | Tenant integrations; secrets never persisted in plaintext. |
| `/api/v1/admin/trading/{halt,resume}`, `/api/v1/admin/instruments/<instrument>/{halt,resume}` | ADMIN | RBAC, reason, request ID, idempotency, immutable audit. |
| `/api/v1/admin/withdrawals/**`, `/admin/reconciliations/` | ADMIN | Financial boundary remains disabled. |
| `/api/v1/tenant/context`, `/users[/imports/**]`, `/integrations/crm/**`, `/integrations/service-tokens/**` | INTERNAL | Tenant/CRM service contract. |
| `/api/user/**` | DEPRECATED | Successors: `/api/v1/auth/`, `/api/v1/me/`, `/api/v1/compliance/`. |
| `/api/trades/**` | DEPRECATED | Successors: `/api/v1/demo/`, `/api/v1/trading/`, `/api/v1/market/`. |
| `/api/orders/**`, `/api/trail-order/` | REMOVE_AFTER_MIGRATION | Provider-specific Alpaca order surface; absent in paper-only deployments. |
| `/api/market-data/alpaca/`, `/api/assets/`, `/api/get-clock/`, `/api/get-calendar/`, `/api/top-market-movers/`, `/api/get-crypto-lates-bars/`, `/api/get-assets/` | DEPRECATED | Successor: normalized `/api/v1/market/**`. |
| `/api/wallet/**` including transactions, wallets, deposit/withdraw/transfer/refill, manual-balance updates | DEPRECATED | Demo-only compatibility; real balance mutation is denied. |
| `/api/payment/**` including Stripe/Binance/payment processing | REMOVE_AFTER_MIGRATION | Real mutation disabled; migrate to Financial Service-backed canonical routes. |
| `/api/notification/**` | COMPATIBILITY | Successor: `/api/v1/notifications/`. |
| `/api/news/**`, `/api/get-news/` | DEPRECATED | Successor: `/api/v1/news`. |
| `/api/admin/**` | ADMIN | Legacy user/KYC/RBAC/ticket administration. |
| `/api/security/**` | ADMIN | Global and per-user security administration. |
| `/api/bank_account/**` | REMOVE_AFTER_MIGRATION | Legacy financial-adjacent surface. |
| `/api/charts/**` | DEPRECATED | Successor: `/api/v1/market/**`. |
| `/api/portfolio/**` | DEPRECATED | Demo projection only; successor `/api/v1/wallets/` and `/api/v1/trading/positions`. |
| `/api/reporting/**` | COMPATIBILITY | Successor: `/api/v1/reports/`. |

## Realtime inventory

| Route | Classification | Migration |
|---|---|---|
| `/ws/v2/` | CANONICAL | Single customer connection through existing Centrifugo/NATS bridge. |
| `/ws/v1/` | COMPATIBILITY | Canonical gateway compatibility only. |
| `/ws/external-api/` | INTERNAL | External integration channel. |
| `/ws/market/`, `/ws/trades/`, `/ws/admin/`, `/ws/users/` | DEPRECATED | Migrate to authenticated `/ws/v2/` channels. |
| `/ws/crypto-market-data/`, `/ws/stock-market-data/`, `/ws/market-data/` | DEPRECATED | Migrate to public `/ws/v2/` market channels. |
| `/ws/asset-data/<user_id>/`, `/ws/current-balance/<user_id>/`, `/ws/profit-loss/<user_id>/` | REMOVE_AFTER_MIGRATION | Client-supplied user IDs are forbidden for new private channels. |
| `/ws/v1/real-wallet/` | INTERNAL | Disabled financial boundary; not a second customer realtime stack. |

## Canonical ownership

- Real trading: `apps.trading`; mutation boundary disabled.
- Demo trading: existing demo engine and server-authored demo account channels.
- Market data: `trade.market_api` normalized contracts.
- Financial value: independently deployed Financial Service only.
- Events: `foundation.OutboxEvent` and the standard versioned envelope.
- Realtime: existing NATS/JetStream → bridge → Centrifugo → `/ws/v2/`.

Legacy HTTP responses receive `Deprecation`, `Sunset`, and successor `Link` headers through `LegacyApiDeprecationMiddleware`; calls are logged and counted by `codestra_legacy_api_requests_total`.
