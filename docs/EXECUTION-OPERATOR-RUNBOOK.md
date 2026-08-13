# Execution Provider Operator Runbook

1. Confirm the environment is local, test, or isolated staging.
2. Confirm all live and real-money flags are false.
3. Inspect `/api/v1/operator/execution/providers` and recent routes.
4. On degraded, ambiguous, or unsafe behavior, halt the provider with a concise incident reason.
5. Preserve route, request, market-snapshot, outbox, audit, and provider evidence.
6. Reconcile all unknown outcomes. Never resubmit or fail over an ambiguous order.
7. Resume only after health and reconciliation are independently verified. Resume is audited and does not authorize live routing.

If a live route or FIX session appears, treat it as a critical incident, halt execution, and preserve evidence. This codebase provides no authorized live transition.
