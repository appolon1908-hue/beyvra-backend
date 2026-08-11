# Liquidation authority

`LiquidationPlanner` is deterministic and simulation-only. It prioritizes margin consumption, skips halted/closed/stale instruments, supports partial reductions, and creates no broker or live-execution request. There is no live execution endpoint.
