# Market Surveillance Inventory

Snapshot: 2026-08-11 UTC. Primary authority is `apps.surveillance` in the Beyvra application backend.

| Control | Prior state | Disposition |
|---|---|---|
| Generic order risk engine | AUTHORITATIVE for limits | Retained; surveillance runs before reservation/routing |
| Platform/instrument trading controls | PARTIAL | Retained at higher precedence |
| Restricted/watch list | MISSING | Added as versioned, effective-dated `TradingRestriction` |
| Self-trade prevention | MISSING | Added with default `REJECT_NEW` policy |
| Wash/spoof/layer/cancel/flip/rate indicators | MISSING | Added deterministic, versioned indicator rules |
| Surveillance cases and evidence | MISSING | Added role-limited cases, hashes, audit and outbox |
| Inbox/dead letter/reconciliation | PARTIAL foundation | Reused canonical foundation and added surveillance checks |
| Customer surveillance UI/API | UNSAFE if exposed | Explicitly absent; safe trading errors only |

Financial Service, frontend state, and provider symbols are not surveillance authority.
