# Full-stack reconciliation

Checks span orders, executions, trades, positions/P&L, fees, treasury, settlement, regulatory records, audit, and outbox. Every nonzero mismatch fails. Runs require an injected immutable release SHA and cannot derive candidate identity from a mutable working directory.
