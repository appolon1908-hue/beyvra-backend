# Valuation and P&L inventory

Reviewed 2026-08-11 against candidate `97b4cbb`.

| Existing component | Classification | Valuation use |
|---|---|---|
| `apps.post_trade.Trade` and `FeeSnapshot` | AUTHORITATIVE (simulation) | Acquisition/disposal and fee evidence |
| `TradePositionEffect` | AUTHORITATIVE (simulation) | Position quantity source |
| Instrument/reference-data authority | AUTHORITATIVE | Stable instrument identity and corporate-action lineage |
| Market-data authority | PARTIAL | Source contract exists; stored valuation evidence was missing |
| Legacy portfolio models | LEGACY/UI projection | Not used as ledger, lot, or P&L authority |
| Financial Service | EXTERNAL AUTHORITY | No direct DB access and no balance mutation |
| FX valuation, lots, basis, P&L, NAV and snapshots | MISSING | Added by this change |

The application owns simulated portfolio accounting. Financial Service remains the financial ledger authority. No model in `apps.valuation` represents real cash or settled assets.

