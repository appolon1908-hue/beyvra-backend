# Position Reconciliation

`PositionReconciler` compares legacy fills to canonical trades, allocations, position effects, obligations, instructions, confirmations, reservations, and audit evidence. It is read-only: violations are persisted as evidence and never trigger automatic financial or historical-record repair.
