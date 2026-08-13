# Position Mismatch

Symptoms: reconciliation reports `POSITION_MISMATCH` or the position accounting invariant rises. Dashboard: Trading Pipeline and Release Readiness. Alert: BeyvraReconciliationIntegrityCritical. Verify with `run_reconciliation --scope positions --format json` and preserve the immutable run ID. Stop new simulation acceptance; do not edit positions or wallets manually. Roll back the implicated simulation release. Escalate to the trading owner. Resume only after reviewed repair tooling, full reconciliation PASS, and stable invariant counters.

Inspect fill, trade, allocation, position effect, reservation, and correction evidence. Open a post-trade exception and prevent automatic progression. Never repair the projection or Financial Service ledger directly; use an independently approved correction flow.
