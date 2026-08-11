# Market Surveillance Architecture

The synchronous path is authentication → account/compliance/trading controls → surveillance restriction authority → self-trade prevention → risk → simulated router. Any hard denial stops before order persistence, reservation, execution, trade, or settlement. Denial evidence commits independently.

Post-trade/window analysis consumes provider-neutral canonical events through `ProcessedEvent`, writes indicator evidence and cases atomically, and emits canonical outbox events. Redis may accelerate future aggregates but is not evidence authority. The current implementation queries PostgreSQL.

Indicators are not legal conclusions. The engine may allow, alert, review, or deny; it cannot close accounts or submit regulatory reports.
