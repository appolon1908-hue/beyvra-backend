# Best Execution and Smart Order Routing Authority

## Scope and safety boundary

This authority is a technical policy, evidence, and measurement layer for simulation and approved paper environments. It is not a legal conclusion that any regulatory best-execution duty is satisfied. Live broker routing and FIX sessions remain unavailable.

The server-enforced invariants are:

- `REAL_TRADING_ENABLED=false`
- `EXTERNAL_EXECUTION_ENABLED=false`
- `LIVE_BROKER_ROUTING_ENABLED=false`
- `FIX_LIVE_SESSION_ENABLED=false`
- live mode is rejected before provider selection
- a provider in `HALTED`, `DEGRADED`, or `UNAVAILABLE` state is ineligible
- no automatic retry or failover follows an ambiguous external mutation

## Decision flow

An order reaches routing only after account, compliance, surveillance, margin, and risk controls. The router evaluates the requested mode, provider health, circuit state, supported order type, asset class and venue. Every decision records the complete candidate set, exclusion reason codes, selected provider and venue, policy version, request hash, market snapshot hash, reference price, and actor scope.

The current seeded authority is `simulation` on `BEYVRA-SIM`. It performs no network requests. Paper adapters may be registered only as separate `PAPER` providers; they cannot become live providers through configuration because live routing is denied in code and settings.

## Best-execution policy

Policy `best-execution-sim-v1` uses deterministic eligibility and score ordering. A score is meaningful only among eligible candidates. Future policy inputs may include authoritative price, explicit fees, likelihood of execution, latency, size, venue restrictions, and client instructions. Missing or stale authoritative inputs must exclude a route rather than be guessed.

Provider failover is permitted only before any submission. A timeout after a possible submission is an `UNKNOWN` outcome: reconcile through provider operation lookup before retry. Automatic routing to a second broker is prohibited for unknown outcomes.

## Execution quality

Measurement `execution-quality-v1` binds the route decision to the average execution price and filled quantity. Side-aware implementation shortfall is:

- buy slippage: `(execution - reference) / reference * 10,000`
- sell slippage: `(reference - execution) / reference * 10,000`
- price improvement is the negative of slippage, expressed as amount and basis points

Reports retain evidence hashes and do not treat simulation results as live execution-quality certification.

## Operator authority

Provider inventory, routes and aggregate reports require an administrator. Halt/resume requires an explicit reason, locks the provider row, writes immutable application audit evidence, and emits a canonical outbox event. Emergency halt is fail-closed. Resume does not and cannot enable live routing.

## API and realtime contracts

User APIs are under `/api/v1/execution/`; operator APIs are under `/api/v1/operator/execution/`. Private quality events use `simulation.execution-quality.{account_id}` through `/ws/v2/`; no provider WebSocket is browser-accessible.

## FIX readiness

Future FIX support must keep session logon, credentials, sequence numbers, resend handling, duplicate execution reports, rejects, reset policy and reconciliation inside a server-side gateway. `FIX_LIVE_SESSION_ENABLED` remains hard false. Fixture and paper sessions must use distinct identities and network destinations.
