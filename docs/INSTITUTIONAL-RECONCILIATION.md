# Institutional reconciliation

The read-only reconciler detects wrong-tenant subaccounts, unattributable
positions, allocation quantity mismatch, omnibus attribution mismatch, and
segregated mapping conflict. It emits audit/outbox evidence but never repairs,
moves, merges, or deletes ownership or financial state.
