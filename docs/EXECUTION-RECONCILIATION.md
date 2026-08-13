# Execution Reconciliation

The reconciler is read-only. It checks provider references, canonical state and quantity consistency, duplicate execution identities, missing trades, unresolved outcomes, route evidence, quality reports, audit, outbox, and inbox evidence.

It emits immutable hashed run evidence with the candidate SHA and `PASS` or `CRITICAL`. Completed runs cannot be edited or deleted. There is no repair endpoint and reconciliation never changes an order, fill, trade, or settlement.
