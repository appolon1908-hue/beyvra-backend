# Execution Inventory

| Surface | Classification | Authority |
|---|---|---|
| `apps.trading.execution_control` | AUTHORITATIVE | Capabilities, governance, policy, routing, state, quality, recovery, health, reconciliation |
| `integrations.execution.simulated` | SIMULATION_ONLY | Deterministic local fills |
| `integrations.execution.paper` | SIMULATION_ONLY | Deterministic paper fixture; no network |
| `integrations.execution.fix_gateway` | FIXTURE_ONLY | Session/sequence/duplicate contracts; no transport |
| `api_trade` broker scripts | LEGACY / PROVIDER_SPECIFIC | Mutation routes structurally removed by `PAPER_TRADING_ONLY=True` |
| `apps.trading.application.simulation` | AUTHORITATIVE | Current order/risk/reservation/fill integration |
| Financial settlement | MISSING / EXTERNAL | Financial Service authority; intentionally unchanged |

No production broker credential, live provider, or live FIX transport is configured.
