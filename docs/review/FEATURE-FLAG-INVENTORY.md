# Feature flag inventory

The checked-out backend defines at least 27 settings or model values resembling feature/activation switches.

## High-risk financial and execution flags

| Flag | Default/evaluator | Status |
|---|---|---|
| `REAL_MONEY_ENABLED` | environment, default false | fail closed |
| `LIVE_TRADING_ENABLED` | environment, default false | duplicate/unused authority |
| `REAL_TRADING_ENABLED` | hardcoded false | fail closed |
| `EXTERNAL_EXECUTION_ENABLED` | hardcoded false | fail closed |
| `REAL_WALLET_READ_ENABLED` | hardcoded false | fail closed |
| `REAL_DEPOSITS_ENABLED` | hardcoded false | fail closed |
| `REAL_WITHDRAWALS_ENABLED` | hardcoded false | fail closed |
| `REAL_INTERNAL_TRANSFERS_ENABLED` | hardcoded false | fail closed |
| `PAYMENTS_ENABLED` | environment, default false | separate legacy capability |

The application system check rejects any enabled real-money gate. Database `real_wallet.FeatureFlag` values cannot override a false settings gate. `LIVE_TRADING_ENABLED` versus `REAL_TRADING_ENABLED` is a high-risk naming duplication and must not become a second evaluator.

