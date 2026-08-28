# Backend Production Completion Map

Canonical domain models, services, migrations, and architecture boundaries for the Beyvra Backend.

## 1. Canonical Authorities and Domain Matrix

| Domain | Canonical Model Authority | Canonical Decision / Computation Service | Existing Endpoints & Aliases | Migration Baseline |
|---|---|---|---|---|
| **Platform Capabilities & Config** | `PlatformConfig`, `TenantEntitlement`, `TradingControl` | `platform_ops.health.services.HealthAggregator`, `apps.trading.application.simulation.simulation_available` | `GET /api/v1/platform/config`, `GET /api/v1/platform/capabilities` (New Canonical) | `platform_ops.0003_converged_controls` |
| **Order Management (OMS)** | `apps.trading.models.TradingOrder`, `OrderPreview`, `OrderEvent` | `apps.trading.application.simulation` (create, preview, cancel), `apps.trading.domain.orders.transition_order` | `POST /api/v1/orders/preview`, `POST /api/v1/orders`, `GET /api/v1/orders`, `GET /api/v1/orders/{id}`, `POST /api/v1/orders/{id}/cancel`, `POST /api/v1/orders/{id}/replace` | `apps.trading.0009_merge_converged_trading_graph` |
| **Financial Ledger & Projections** | `financial_boundary.models.FinancialLedger`, `financial_boundary.models.FinancialReservation` | `financial_boundary.services.FinancialProjectionService`, `apps.valuation.services.ValuationService` | `GET /api/v1/accounts`, `GET /api/v1/accounts/{id}/balances`, `GET /api/v1/accounts/{id}/buying-power`, `GET /api/v1/accounts/{id}/tax-lots` | `financial_boundary.0005_financial_halt_authority` |
| **Market Data & Instruments** | `reference_data.models.Instrument`, `pricing_authority.models.MarketPrice` | `reference_data.services.InstrumentResolver`, `pricing_authority.services.PriceAuthority` | `GET /api/v1/instruments`, `GET /api/v1/markets/status`, `GET /api/v1/market/snapshot`, `GET /api/v1/market/candles` | `reference_data.0004_converged_instruments` |
| **Watchlists & Alerts** | `apps.workspace.models.Watchlist`, `apps.workspace.models.WatchlistItem`, `notifications.models.Alert` | `apps.workspace.services.WatchlistService`, `notifications.services.AlertService` | `PATCH /api/v1/watchlists/{id}`, `PATCH /api/v1/watchlists/{id}/items/reorder`, `POST /api/v1/alerts` | `apps.workspace.0003_watchlist_versioning` |
| **Compliance & Risk** | `apps.compliance.models.ComplianceProfile`, `apps.compliance.models.ComplianceDecision` | `apps.compliance.services.get_trading_eligibility`, `apps.trading.risk.RiskEngine` | `GET /api/v1/compliance/status`, `GET /api/v1/compliance/requirements`, `POST /api/v1/compliance/acknowledgements` | `apps.compliance.0014_override_constraints` |
| **Realtime Event Stream** | `apps.foundation.models.OutboxEvent`, `ws.v2.models.StreamSequence` | `ws.v2.services.RealtimeDispatcher`, `ws.v2.consumers.UnifiedStreamConsumer` | `GET /api/v1/realtime/snapshot`, `GET /api/v1/realtime/resume`, `POST /api/v1/realtime/ticket` | `apps.foundation.0005_outbox_ordering` |
| **Provider Webhooks** | `financial_boundary.models.WebhookInbox`, `financial_boundary.models.WebhookDeadLetter` | `financial_boundary.webhooks.WebhookIngestionService` | `POST /api/v1/webhooks/executions/{provider}`, `POST /api/v1/webhooks/market-data/{provider}` | `financial_boundary.0002_event_boundary` |

---

## 2. Authentication, Tenancy & Security Boundaries

* **BFF Session Model**: Session and JWT tokens are managed with `HttpOnly`, `SameSite=Lax`, `Secure` cookies.
* **Tenant Isolation**: Every financial query must filter by `tenant_ref` and `subject_ref`. Cross-tenant lookups fail closed with `404 Not Found`.
* **Idempotency**: All mutating state commands require `Idempotency-Key` persisted in PostgreSQL with atomic row leases.
* **Non-Negotiable Live Capability Lock**:
  ```ini
  LIVE_TRADING_ENABLED=false
  REAL_MONEY_ENABLED=false
  DEPOSITS_ENABLED=false
  WITHDRAWALS_ENABLED=false
  EXTERNAL_EXECUTION_ENABLED=false
  CUSTODY_ENABLED=false
  ```

---

## 3. Legacy Route Delegation & Deprecation Map

* Legacy `/api/trades/` delegates to canonical `apps.trading.api.views.TradesView`.
* Legacy `/api/portfolio/summary/` delegates to canonical `apps.valuation.portfolio_api.PortfolioSummaryView`.
* Legacy direct balance manipulation routes are disabled and return HTTP 503 `FEATURE_DISABLED`.

---

## 4. Test Entry Points

* `FX/apps/trading/tests/` (Execution authority, simulation E2E, reconciliation)
* `FX/platform_ops/tests/` (Health, degraded mode, kill switch, capacity)
* `FX/financial_boundary/tests/` (Financial ledger, idempotency, webhook ingestion)
* `FX/apps/valuation/tests/` (PNL, NAV, portfolio projections)
* `FX/apps/compliance/tests/` (Eligibility, overrides, sanctions, KYC)
