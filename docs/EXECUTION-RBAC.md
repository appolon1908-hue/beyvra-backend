# Execution RBAC

Customer endpoints require authentication and tenant-owned orders. Operator access uses distinct groups:

- `execution_viewer` reads inventory, health, routes, quality, and reconciliation evidence.
- `execution_operator` may halt/resume paper providers and run reconciliation.
- `execution_manager` may request and independently approve paper-governance changes.

Paper enablement persists a `PENDING` governance change. The requester cannot approve it; a different manager must act as checker. Live enablement has no API. Emergency halt is immediate, while resume still cannot override global halt, governance, capability, health, environment, or live-mode denial.
