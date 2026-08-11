# Provider certification

Certification date: 2026-08-11. No outbound provider call was authorized or made (`NO_OUTBOUND_PROVIDER_TEST=YES`). Capability review used official vendor documentation; entitlement columns require account-owner/legal evidence and therefore remain NO.

| Provider | Capability review | Credential present | License | Security | Staging | REST | WebSocket | Rate limit | Reconnect | Data quality | Production |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CoinGecko | PASS | NOT INSPECTED | NO | NO | NO | FIXTURE CONTRACT ONLY | NOT AUTHORIZED | FIXTURE | FIXTURE | FIXTURE | NO |
| Massive/Polygon | PASS | NOT INSPECTED | NO | NO | NO | FIXTURE CONTRACT ONLY | NOT AUTHORIZED | FIXTURE | FIXTURE | FIXTURE | NO |
| NewsData.io | PASS | NOT INSPECTED | NO | NO | NO | FAIL-CLOSED FIXTURE | N/A | FIXTURE | N/A | FIXTURE | NO |
| Alpaca market data | PASS | NOT INSPECTED | NO | NO | NO | FIXTURE CONTRACT ONLY | NOT AUTHORIZED | FIXTURE | FIXTURE | FIXTURE | NO |
| Binance | code inventory | NOT INSPECTED | NO | NO | NO | FIXTURE | FIXTURE | FIXTURE | FIXTURE | PASS | NO |
| Twelve Data | code inventory | NOT INSPECTED | NO | NO | NO | FIXTURE | NOT AUTHORIZED | FIXTURE | FIXTURE | PASS | NO |

Official review notes: CoinGecko supports REST/WebSocket but WebSocket and endpoint access are plan-dependent, with ping/pong and reconnect guidance. Massive supports REST/WebSocket, delayed and realtime clusters, with product/plan entitlements and selected LULD availability. Alpaca separates market-data streams, paper trading, and live trading; paper is simulation, not live certification. NewsData uses API-key/credit rate limits and its terms control redistribution. Capability is not Beyvra entitlement.

Fixture certification covers malformed data, idempotent canonical persistence, canonical quote/trade/status endpoints, fail-closed empty authority, dedupe, out-of-order aggregation, stale gates, rate limiting/Retry-After, bounded jittered backoff, failover/split brain, and snapshot reconciliation. Live staging remains blocked on credential owner, license, security, compliance, and staging approvals.

Final isolated results: provider/governance suite `41/41`; complete backend inventory `228` tests (227 in one run plus the sole infrastructure-interrupted test rerun successfully after a disposable PostgreSQL layer reported disk exhaustion); frontend unit suite `84/84`; frontend lint, typecheck, safe-error checks, and production build pass. PostgreSQL 16 migration-from-zero, rollback, and reapply pass. No outbound provider or execution call occurred.
