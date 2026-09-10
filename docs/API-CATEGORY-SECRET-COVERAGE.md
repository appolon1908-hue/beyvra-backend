# Beyvra API categories and secret boundaries

This source review uses the 13 requested API categories. Route presence is not a
claim of a complete feature, a provider contract or a live integration. The
machine-readable map is `docs/API-CATEGORY-SECRET-COVERAGE.v1.json`.

| # | API category | Source routing | Secret workload | Remaining verification / gap |
| --- | --- | --- | --- | --- |
| 1 | Authentication and permissions | `FX/users/urls.py`, `FX/security/urls.py` | `beyvra-api` | Keycloak runtime SSO/MFA and per-account access require live verification. |
| 2 | Customer onboarding / KYC | `FX/users/urls.py`, `FX/apps/compliance/urls.py` | `beyvra-api` | KYC routes and compliance source exist; provider-backed verification and account-opening certification are unverified. No dedicated KYC provider credential is admitted yet. |
| 3 | Instruments and market information | `FX/reference_data/urls.py` | `beyvra-market-data` | Provider symbol mapping, asset-class coverage and trading calendars require provider evidence. |
| 4 | Market data | `FX/trade/market_urls.py`, `FX/pricing_authority/urls.py` | `beyvra-market-data` | Live price freshness, streaming entitlements and order-book coverage are unverified. |
| 5 | Orders and execution | `FX/apps/trading/api/urls.py`, `FX/apps/trading/api/execution_urls.py` | `beyvra-trading-executor` | PAPER_TRADING_ONLY remains true. Live broker order execution is not enabled or certified. |
| 6 | Accounts and balances | `FX/apps/trading/api/urls.py`, `FX/financial_boundary/urls.py` | `beyvra-api` | Account detail uses EmptyDetailView. Broker-backed account balances and read-only broker entitlements require separate admission. |
| 7 | Positions and portfolio | `FX/apps/valuation/urls.py`, `FX/portfolio/urls.py` | `beyvra-api` | Some valuation/performance routes use Disabled. Reconciled live holdings and performance are unverified. |
| 8 | Funding and transfers | `FX/financial_boundary/urls.py`, `FX/treasury/urls.py` | `beyvra-funding` | Real-value features remain gated. Funding provider selection, beneficiary checks and reconciled bank transfers are unverified. |
| 9 | Risk controls | `FX/risk_authority/urls.py` | `beyvra-api` | Several exposure, buying-power and margin routes use FeatureDisabledView. Full pre-trade risk enforcement needs certification. |
| 10 | Research and watchlists | `FX/apps/workspace/urls.py`, `FX/news_app/urls.py` | `beyvra-market-data` | Provider licensing, fundamentals and calendar completeness require verification. |
| 11 | Notifications and events | `FX/notifications/urls.py`, `FX/wsnotifications/urls.py` | `beyvra-api` | Notification delivery and event replay require runtime evidence. Shared email/SMS provider master keys belong to their admitted adapters. |
| 12 | Reports and audit history | `FX/apps/post_trade/urls.py`, `FX/reporting/urls.py`, `FX/operations/urls.py` | `beyvra-api` | Complete statements, confirmations and jurisdiction-specific tax documents are not certified by route presence. |
| 13 | Operations and monitoring | `FX/platform_ops/public_urls.py`, `FX/platform_ops/operator_urls.py`, `FX/platform_ops/health/urls.py` | `beyvra-api` | Runtime provider health, execution latency and reconciliation alerting are unverified. |

Secret-workload assignments describe the intended provider boundary. Runtime
secret delivery is implemented separately in `openbao-secret-consumer.v1.json`.
KYC credentials and read-only broker account credentials need exact provider
admission once the selected integrations and permissions are verified; the map
does not silently give account readers the order-execution token.

Application sessions, KYC documents, account balances, orders, positions and
funding transactions belong to their domain services and databases. OpenBao
holds infrastructure and provider secrets, not that business data. User tokens
and short-lived provider OAuth tokens must not become durable KV records.

REST/HTTPS, WebSocket, webhook and FIX are transport choices. They do not replace
tenancy, authentication, order idempotency, risk controls or reconciliation.
FIX is not introduced without a broker requirement. No live order, payment,
email or SMS effect is enabled by this secret-storage change.
