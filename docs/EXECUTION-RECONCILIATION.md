# Execution Reconciliation

The reconciler is read-only and detects unresolved outcomes, missing route evidence, missing quality reports, audit gaps and outbox gaps. It emits immutable hashed run evidence with `PASS` or `CRITICAL`; there is no repair endpoint.
