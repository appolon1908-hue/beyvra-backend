# Financial incident response

Incident types include unknown outcome, duplicate effect, reconciliation mismatch, provider incident and withdrawal-security incident. Evidence records severity, type, detection time, candidate SHA, environment, safe summary, status, resolution time and evidence hash.

Logical halt states are `ACTIVE`, `READ_ONLY`, `WITHDRAWALS_HALTED`, `FUNDING_HALTED`, `ALL_MUTATIONS_HALTED`. These can only reduce capability; disabled real-money flags always win. Preserve evidence, stop affected workflows, query authoritative state, reconcile, and require independent approval before recovery.

The application records halt requests and approvals as separate append-only PostgreSQL records under policy `financial-halt-v1`. A maker needs `financial_operations` or `financial_manager`; the independent checker must have `financial_manager`. Generic support and `financial_viewer` cannot request or approve a halt, and self-approval is denied. Each request and approval also creates an append-only financial audit entry. PostgreSQL triggers deny direct update/delete of halt history.

Approval is tenant-scoped, idempotent, and serialized with a transaction-scoped advisory lock. A proposed state must be strictly no less restrictive than the effective state; competing requests cannot re-enable an operation. `WITHDRAWALS_HALTED` denies withdrawals, `FUNDING_HALTED` denies deposits, and `READ_ONLY`/`ALL_MUTATIONS_HALTED` deny every modeled financial mutation. This module exposes no recovery or activation operation during this mission. A future integration must call the halt authority after resolving authenticated tenant identity and before constructing a Financial Service/provider mutation.
