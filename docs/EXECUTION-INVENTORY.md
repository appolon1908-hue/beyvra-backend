# Execution Inventory

| Surface | Classification | Authority |
|---|---|---|
| `apps.trading.execution_control` | AUTHORITATIVE | Distinct capability, governance, policy, routing, state, quality, recovery, health, and reconciliation services |
| `integrations.execution.simulated` | SIMULATION_ONLY | Deterministic local fills |
| `integrations.execution.paper` | SIMULATION_ONLY | Deterministic paper fixture; no network |
| `integrations.execution.fix_gateway` | FIXTURE_ONLY | Session/sequence/duplicate contracts; no transport |
| `api_trade` broker scripts | LEGACY / PROVIDER_SPECIFIC | Mutation routes structurally removed by `PAPER_TRADING_ONLY=True` |
| `apps.trading.application.simulation` | AUTHORITATIVE | Current order/risk/reservation/fill integration |
| Financial settlement | MISSING / EXTERNAL | Financial Service authority; intentionally unchanged |

The Alpaca legacy modules are not inputs to route selection. Their mutation URLs are absent while the hard `PAPER_TRADING_ONLY` setting is active; they remain unsafe as execution authority and must not be re-enabled directly.

No production broker credential, live provider, live FIX transport, live settlement path, or regulatory best-execution approval is configured or claimed.
