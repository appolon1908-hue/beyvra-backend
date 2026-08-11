# Position Mismatch

Symptoms: reconciliation reports `POSITION_MISMATCH` or the position accounting invariant rises. Dashboard: Trading Pipeline and Release Readiness. Alert: BeyvraReconciliationIntegrityCritical. Verify with `run_reconciliation --scope positions --format json` and preserve the immutable run ID. Stop new simulation acceptance; do not edit positions or wallets manually. Roll back the implicated simulation release. Escalate to the trading owner. Resume only after reviewed repair tooling, full reconciliation PASS, and stable invariant counters.
