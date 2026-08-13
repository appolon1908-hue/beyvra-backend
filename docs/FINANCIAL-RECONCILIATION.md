# Financial reconciliation

The engine is read-only and compares application intent, authoritative operation, reservation, settlement, deposit, withdrawal, transfer, wallet projection, outbox, inbox and audit.

It reports: `MISSING_FINANCIAL_OPERATION`, `DUPLICATE_FINANCIAL_EFFECT`, `ORPHAN_RESERVATION`, `RESERVATION_LEAK`, `SETTLEMENT_MISMATCH`, `WALLET_PROJECTION_MISMATCH`, `DEPOSIT_CREDIT_MISMATCH`, `WITHDRAWAL_STATE_MISMATCH`, `TRANSFER_STATE_MISMATCH`, `AUDIT_GAP`.

Critical findings block readiness, alert, and create immutable incident evidence. Reconciliation never repairs or posts ledger entries automatically.

Canonical evidence includes `financial_outbox`, `financial_inbox`,
`financial_dead_letters`, and `financial_audit`. An outbox row beyond its retry
policy, an authoritative event without an inbox receipt, or an intent without
an audit record is evidence for `AUDIT_GAP` or the corresponding operation
mismatch. Automated repair remains forbidden.

## Executable evidence contract

`ReconciliationEvidence` accepts immutable tuples for application and
Financial Service operations, reservations, application/financial settlement
pairs, wallet projections/snapshots, deposit pairs, withdrawal pairs, transfer
pairs, outbox, received events, inbox receipts, and audit records.

One run always reports all ten check authorities:

1. `MISSING_FINANCIAL_OPERATION`
2. `DUPLICATE_FINANCIAL_EFFECT`
3. `ORPHAN_RESERVATION`
4. `RESERVATION_LEAK`
5. `SETTLEMENT_MISMATCH`
6. `WALLET_PROJECTION_MISMATCH`
7. `DEPOSIT_CREDIT_MISMATCH`
8. `WITHDRAWAL_STATE_MISMATCH`
9. `TRANSFER_STATE_MISMATCH`
10. `AUDIT_GAP`

Valid 10,000-row deterministic evidence must produce zero findings. Each
violation has a dedicated fixture. Inputs are deep-compared after execution to
prove the engine does not mutate them.

Any finding makes `activation_ready=false`. The report creates a SHA-256
evidence digest and can build a bounded incident candidate containing only the
candidate SHA, environment, count, status, and digest. References and raw
financial records are excluded from the incident summary. Incident persistence
and alert delivery are explicit orchestration steps; the reconciliation engine
has no ledger, provider, or automatic repair method.
