# Financial reconciliation

The engine is read-only and compares application intent, authoritative operation, reservation, settlement, deposit, withdrawal, transfer, wallet projection, outbox, inbox and audit.

It reports: `MISSING_FINANCIAL_OPERATION`, `DUPLICATE_FINANCIAL_EFFECT`, `ORPHAN_RESERVATION`, `RESERVATION_LEAK`, `SETTLEMENT_MISMATCH`, `WALLET_PROJECTION_MISMATCH`, `DEPOSIT_CREDIT_MISMATCH`, `WITHDRAWAL_STATE_MISMATCH`, `TRANSFER_STATE_MISMATCH`, `AUDIT_GAP`.

Critical findings block readiness, alert, and create immutable incident evidence. Reconciliation never repairs or posts ledger entries automatically.
