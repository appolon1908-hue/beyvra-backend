# API and Webhook Gap Register

| Gap | Severity | Status | Closure |
|---|---|---|---|
| Fragmented public resource routes | P1 | FIXED | Canonical platform URL layer delegates to existing domain authorities. |
| Missing account sessions/security events | P1 | FIXED | Tenant-scoped session/revocation and safe security-event records. |
| Missing notification preferences/support/report/privacy workflows | P1 | FIXED | Canonical resources with validation, idempotency, outbox, and tenant tests. |
| Missing operator maker/checker contract | P1 | FIXED | Scoped roles, independent approval, immutable audit, and outbox. |
| Generic provider webhook boundary absent | P1 | FIXED | Signature/timestamp/replay/inbox/dead-letter/rotation contract. |
| `/ws/v2/` advertised but not routed by ASGI | P0 | FIXED | Authenticated v2 routes and required event envelope added. |
| Frontend duplicate realtime event application | P1 | FIXED | Duplicate/stale sequence suppression plus snapshot gap recovery. |
| Legacy payment endpoints could reach provider | P0 | FIXED | Immutable real-money/deposit authority checked before provider logic. |
| Request/correlation identifiers exposed publicly | P1 | FIXED | Removed from canonical errors, wallet errors, and response headers. |
| Frontend caller fragmentation | P1 | FIXED | Canonical notification/demo/report callers; remaining compatibility callers classified. Unmapped count zero. |
| External custody/payment/execution activation | P1 | BLOCKED_EXTERNAL | Requires independent legal, security, compliance, financial, and provider approvals. No activation attempted. |
| Production deployment | P1 | BLOCKED_EXTERNAL | Explicitly prohibited by mission boundary. |

`API_P0_OPEN=0` and `WEBHOOK_P0_OPEN=0`. No technically solvable P1 item is left as TODO.
