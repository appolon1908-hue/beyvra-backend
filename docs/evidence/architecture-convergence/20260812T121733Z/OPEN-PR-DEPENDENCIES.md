# Open PR dependency baseline

Read through authenticated GitHub metadata on `2026-08-12`. No remote state was changed.

## Backend mission stacks

| PR | Head | Base | GitHub merge state |
|---:|---|---|---|
| 20 | `security/backend-p0-remediation` | `main` | clean |
| 21 | `feat/canonical-api-realtime-prep` | `security/backend-p0-remediation` | clean |
| 22 | `feat/simulated-e2e-trading` | `feat/canonical-api-realtime-prep` | clean |
| 23 | `feat/simulated-trading-chaos-harness` | `feat/simulated-e2e-trading` | clean |
| 24 | `feat/trading-observability-readiness` | `feat/simulated-trading-chaos-harness` | clean |
| 26 | `feat/provider-market-data-readiness` | `feat/trading-observability-readiness` | clean |
| 32 | `feat/newsdata-news-integration` | `feat/provider-market-data-readiness` | clean |
| 33 | `feat/core-trading-provider-readiness` | `feat/newsdata-news-integration` | clean |
| 35 | `feat/instrument-reference-data-authority` | `feat/core-trading-provider-readiness` | clean |
| 36 | `feat/pricing-entitlement-authority` | `feat/instrument-reference-data-authority` | clean |
| 37 | `feat/margin-collateral-exposure-authority` | `feat/pricing-entitlement-authority` | clean |
| 39 | `feat/market-surveillance-abuse-controls` | `feat/instrument-reference-data-authority` | clean |
| 41 | `feat/post-trade-settlement-authority` | `feat/market-surveillance-abuse-controls` | clean |
| 44 | `feat/valuation-pnl-performance-authority` | `feat/post-trade-settlement-authority` | clean |
| 38 | `feat/execution-routing-authority` | `feat/trading-observability-readiness` | clean |
| 40 | `feat/best-execution-smart-order-routing` | `feat/execution-routing-authority` | clean |
| 27 | `feat/compliance-account-state-readiness` | `main` | clean |
| 31 | `feat/full-api-webhook-certification` | `feat/compliance-account-state-readiness` | clean |
| 42 | `feat/institutional-account-clearing-authority` | `feat/full-api-webhook-certification` | unstable |
| 29 | `feat/operational-product-control-plane` | `main` | clean |
| 30 | `feat/isolated-staging-integration-certification` | `feat/operational-product-control-plane` | conflicting |
| 34 | `feat/polygon-oms-integration-readiness` | `feat/isolated-staging-integration-certification` | clean |
| 43 | `feat/treasury-liquidity-authority` | `main` | clean |
| 45 | `feat/platform-sre-release-safety` | `feat/treasury-liquidity-authority` | clean |

The PR graph is not one linear integration stack. Clean pairwise PR status does not prove that sibling mission stacks merge or behave coherently together.

## Frontend

Open mission PRs include separate stacks for canonical API/realtime and charts (`#4`-`#10`), compliance/API certification (`#12`, `#16`), operational control (`#13`, `#15`), news/provider UI (`#17`, `#18`), authentication hardening (`#14`), and custodial money movement (`#19`). Frontend PR `#5` is currently conflicting.

## Financial repositories

- Financial Service PRs `#5`, `#6`, and `#7` all target `main`, remain draft, require review, and are individually mergeable.
- Financial governance PRs `#1` and `#3` target `main`, remain draft, require review, and are individually mergeable.

