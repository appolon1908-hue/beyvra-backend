# FIX readiness

`FixExecutionGateway` covers logon/logout, heartbeat, NewOrderSingle, cancel, replace, recovery, execution reports, and rejects. A future implementation must persist inbound/outbound sequence numbers, honor resend ranges and PossDup semantics, deduplicate executions by stable identity, reconcile after disconnect, and govern session resets.

FIX is institutional order-routing infrastructure, not automatically market-data, account, or ledger authority. IBKR requires onboarding and supervised certification for direct FIX connectivity. This repository opens no FIX session and has no broker credentials.

