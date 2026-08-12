# Kill-Switch Inventory

`GLOBAL_PLATFORM_HALT` is the parent of every scoped switch. Unknown or missing high-risk switch state evaluates active. Deactivation uses maker/checker approval.

| Parent | Scoped switch | Protected capability |
|---|---|---|
| `GLOBAL_PLATFORM_HALT` | `TRADING_HALT` | order admission |
| `GLOBAL_PLATFORM_HALT` | `EXECUTION_HALT` | execution and routing |
| `GLOBAL_PLATFORM_HALT` | `SETTLEMENT_HALT` | settlement workflow |
| `GLOBAL_PLATFORM_HALT` | `WITHDRAWAL_HALT` | withdrawals |
| `GLOBAL_PLATFORM_HALT` | `TREASURY_HALT` | treasury actions |
| `GLOBAL_PLATFORM_HALT` | `MARKET_DATA_PROVIDER_HALT` | provider ingestion |
| `GLOBAL_PLATFORM_HALT` | `NEWS_PROVIDER_HALT` | provider ingestion |
| `GLOBAL_PLATFORM_HALT` | `DEVELOPER_API_HALT` | developer API |
| `GLOBAL_PLATFORM_HALT` | `REALTIME_HALT` | realtime publication |

Canonical implementation: `platform_ops.kill_switch.hierarchy` and the append-only `KillSwitch` control plane. `KILL_SWITCH_BYPASS_PATHS=0` for certified services.
