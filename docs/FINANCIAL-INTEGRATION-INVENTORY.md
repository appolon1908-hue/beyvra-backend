# Financial integration inventory

Live discovery date: 2026-08-11 UTC. Candidate: `appolon1908-hue/backend`, branch base `origin/feat/real-wallet-ledger-boundary-20260804`, head `3a7e5132809c65c54229fc5ce77eae6de3d8d777`. Financial Service: `Codestra-SRL/codestra-financial-service`, `feat/financial-boundary-foundation`, `e27b9f67efca3dde5cb295712cb556133e4c00b3`.

| Area | Location | Classification | Disposition |
|---|---|---|---|
| Canonical application API | `financial_boundary` | FINANCIAL_SERVICE_DELEGATED | Disabled, versioned, no local financial mutation |
| Private service client | `financial_client` | CANONICAL | HTTPS/mTLS only; no database API |
| Real wallet/ledger models and services | `real_wallet` | LEGACY / DIRECT_DB_UNSAFE for financial authority | Quarantined below `/api/v1/legacy-real-wallet/`; never canonical |
| Demo wallet/order engine | `trade.demo_engine`, `wallet` | SIMULATED | Separate virtual-money domain |
| Legacy bank withdrawal | `bank_account_app` | LEGACY | Must remain disabled; not a canonical route |
| Legacy payment/Stripe | `payments`, frontend `api/srtipe` | LEGACY | Payment network disabled; frontend stub rejects |
| Provider adapters | `real_wallet.providers`, `financial_boundary.providers` | SIMULATED / CANONICAL | Disabled by default; deterministic sandbox only in tests |
| Reconciliation | `financial_boundary.reconciliation` | CANONICAL | Read-only, ten disagreement types |
| Inbox/dead-letter/incidents | `financial_boundary.models` | CANONICAL | Application metadata only, no balances/ledger |
| Frontend wallet hooks | `src/api/wallet` | LEGACY / SIMULATED | Application API only; financial UX blocks real actions |
| Admin wallet approvals | `real_wallet.views` | LEGACY | Quarantined; cannot activate canonical flow |

Search covered routes, models, services, workers, consumers, flags, provider clients, deployment configuration and frontend callers using the mission vocabulary. No application `DATABASES` alias for Financial PostgreSQL exists. The canonical boundary imports neither `real_wallet.models` nor database drivers.
