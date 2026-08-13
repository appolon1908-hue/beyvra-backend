# Canonical Trading Model Matrix

| Concept | Canonical model/module | Canonical service | Legacy/read/provider variants | Disposition |
|---|---|---|---|---|
| Order | `apps.trading.TradingOrder` | `apps.trading.application.simulation` | `trade.Trade` historical fixed-duration demo rows | legacy model read-only; create/cancel routes removed |
| Order preview | canonical order payload, not persisted | `apps.trading.application.simulation.preview` | old demo quote calculation | superseded |
| Reservation | `apps.trading.SimulatedReservation` for simulation; Financial Service for real value | `SimulatedFinancialAdapter` | frozen real-wallet holds | frozen/not installed |
| Execution | canonical execution-control records plus canonical execution event identity | `apps.trading.execution_control` and simulation application service | provider executions | mapping/evidence only |
| Fill | `apps.trading.SimulatedTrade.execution_id` and post-trade capture identity | `apply_execution` / `process_simulated_fill` | provider fill IDs | references only |
| Trade | `apps.post_trade.Trade` | `apps.post_trade.processor` | `apps.trading.SimulatedTrade` execution projection; `trade.Trade` legacy; `reporting.Trade` read model | roles explicitly separated |
| Allocation | `apps.post_trade.TradeAllocation` | post-trade allocation service | institutional mappings | references/read models |
| Position | `apps.trading.SimulatedPosition` | `SimulatedFinancialAdapter.settle_trade` | `TradePositionEffect`, valuation and portfolio views | projections/evidence only |
| Settlement instruction | `apps.post_trade.SettlementInstruction` | post-trade settlement workflow | institutional/provider settlement mappings | provider-neutral intent/reference only |
| Monetary settlement | Financial Service | external owner contract | backend status/evidence | no backend mutation authority |

The domain dataclasses in `apps.trading.domain` express invariants and are not a
second persistence authority. Provider objects cannot create canonical business
truth except through the canonical application service and idempotent event
path.

```text
DUPLICATE_WRITABLE_ORDER_MODELS=0
DUPLICATE_WRITABLE_EXECUTION_MODELS=0
DUPLICATE_WRITABLE_FILL_MODELS=0
DUPLICATE_WRITABLE_TRADE_MODELS=0
DUPLICATE_WRITABLE_POSITION_MODELS=0
POSITION_AUTHORITIES=1
SETTLEMENT_AUTHORITY_CONFLICTS=0
```
