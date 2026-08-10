# Simulated end-to-end trading

This release proves the canonical order architecture without enabling live execution or real financial effects. Simulation is a separate capability controlled by `SIMULATED_TRADING_ENABLED`; Django rejects that flag outside `local`, `test`, and `staging`. The immutable safety flags `REAL_TRADING_ENABLED`, `EXTERNAL_EXECUTION_ENABLED`, and `REAL_MONEY_ENABLED` remain false.

## Boundary and authority

An authenticated caller must explicitly send `X-Beyvra-Simulation-Mode: true`. The server also requires an allowed deployment environment and the simulation feature flag. This intent header is not a credential and grants nothing when server-side simulation is disabled. Simulation accounts, reservations, balances, trades, and positions live exclusively in the application database under `Simulated*` models. The adapter in `integrations/financial/simulated.py` never imports, reads, or calls Financial Service.

The execution adapter is deterministic and has no network transport. Staging/test configuration selects one of `IMMEDIATE_FULL_FILL`, `PARTIAL_THEN_FILL`, `OPEN_THEN_CANCEL`, `REJECT`, or `EXPIRE`. Prices come only from the explicitly labeled `SIMULATED_EXECUTION_PRICES` fixture map. Every emitted payload carries `simulation: true`.

## Canonical workflow

1. `POST /api/v1/trading/orders/preview` validates the request and returns an ALLOW, DENY, or REVIEW risk result without an order, reservation, trade, or outbox mutation.
2. `POST /api/v1/trading/orders` requires an idempotency key. An allowed request atomically writes the order, risk decision, simulation reservation, audit record, and transactional outbox event.
3. The existing outbox publisher delivers the standard envelope to JetStream. `simulation_consumer.py` invokes the deterministic provider and consumes executions through the existing `ProcessedEvent` inbox.
4. Execution processing locks the order and reservation, creates one canonical simulated trade per execution ID, settles virtual funds, updates the simulated position, and emits order/trade/position/balance projection events in one transaction.
5. Authenticated `/ws/v2/` private channels enforce the server-derived `sim:<user-id>` account scope. Clients replace local state from canonical REST reads after a sequence gap.

## Operations

Recommended staging settings:

```text
DEPLOYMENT_ENV=staging
SIMULATED_TRADING_ENABLED=true
SIMULATED_EXECUTION_SCENARIO=IMMEDIATE_FULL_FILL
SIMULATED_EXECUTION_INLINE=false
REAL_TRADING_ENABLED=false
EXTERNAL_EXECUTION_ENABLED=false
REAL_MONEY_ENABLED=false
```

Use the existing outbox publisher and simulation consumer workers. Monitor `simulated_orders_total`, `simulated_fills_total`, `simulated_rejections_total`, `simulated_cancellations_total`, `simulation_execution_latency_seconds`, outbox backlog, consumer lag, and duplicate-event counts separately from any future live metrics.

Rollback is application-only: disable `SIMULATED_TRADING_ENABLED`, stop the simulation consumer, and deploy the previous immutable backend/frontend commits. Do not roll back or modify Financial Service. Database rollback of `canonical_trading.0002_simulated_trading` is appropriate only after simulation workers are stopped and preservation requirements for staging evidence are satisfied.
