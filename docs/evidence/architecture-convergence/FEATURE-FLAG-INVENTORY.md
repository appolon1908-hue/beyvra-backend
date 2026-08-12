# High-Risk Feature Flag Inventory

All high-risk flags are canonical Django settings, default to literal `False`, and are inspected by the fail-closed system check and `platform_ops.feature_flags.evaluator`.

| Capability | Canonical flag | Default | Invalid/missing behavior | Aliases |
|---|---|---:|---|---|
| Real trading | `REAL_TRADING_ENABLED` | false | false | none |
| External execution | `EXTERNAL_EXECUTION_ENABLED` | false | false | none |
| Monetary settlement | `REAL_SETTLEMENT_ENABLED` | false | false | none |
| Real money | `REAL_MONEY_ENABLED` | false | false | none |
| Withdrawals | `REAL_WITHDRAWALS_ENABLED` | false | false | none |
| Treasury transfer | `REAL_TREASURY_TRANSFERS_ENABLED` | false | false | none |
| Broker routing | `LIVE_BROKER_ROUTING_ENABLED` | false | false | none |
| FIX live session | `FIX_LIVE_SESSION_ENABLED` | false | false | none |

`DUPLICATE_HIGH_RISK_FEATURE_FLAGS=0`; `HIGH_RISK_FLAG_FAIL_OPEN_PATHS=0`.
