# Valuation snapshots, reconciliation, corrections, and audit

Snapshots bind the valuation time, market-data cutoff, policy versions, NAV components, P&L, quality, and a deterministic evidence hash. Immutable evidence models reject update and delete operations.

`ValuationReconciler` is read-only. It checks position/lot quantity, NAV arithmetic, and audit presence; its result is persisted separately. It never repairs lots, trades, balances, NAV, or P&L.

Corrections are append-only requests. A different approver is required; approval does not overwrite the original snapshot. New corrected price/FX evidence or a new restated snapshot must supersede the original explicitly.

Evidence trace: canonical trade → tax lot/disposition → cost basis → valuation price and FX references → realized/unrealized P&L → NAV → performance snapshot.

