# Dead-code register

| Component | Classification | Evidence still required |
|---|---|---|
| `publish_news_calendar_events` compatibility command | LEGACY_IN_USE/DEPRECATED | deployment command references |
| `/api/wallet/*`, `/api/payment/*`, `/api/trades/*` | LEGACY_IN_USE | frontend and external consumer inventory |
| `deposite` route alias | PROBABLY_DEAD | access logs and client search |
| legacy WebSocket consumer families | LEGACY_IN_USE | runtime connection metrics |
| `reporting.Trade` and legacy portfolio models | UNKNOWN | job/admin/report queries |
| `LIVE_TRADING_ENABLED` | PROBABLY_DEAD | full branch/config search |

Nothing classified `UNKNOWN` or `LEGACY_IN_USE` is authorized for deletion.

