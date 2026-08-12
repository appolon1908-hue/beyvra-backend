# Module dependency and authority graph

Canonical direction:

`Identity -> Accounts -> Reference Data / Market Data -> Risk / Pricing -> Orders -> Execution -> Post-Trade -> Positions -> Valuation -> Treasury -> Regulatory Evidence`

Financial Service is a separate monetary authority. The backend may consume its authenticated API/events but must never import its database or recreate a writable real ledger. Developer platform, notifications, reporting, and observability are cross-cutting consumers and may not mutate upstream business truth.

## Detected illegal or ambiguous directions

- Legacy wallet/payment modules mutate balance independently of the Financial Service boundary.
- Legacy trade/provider APIs expose provider-native order behavior beside the canonical trading service.
- Portfolio, reporting, and frontend code derive position/P&L-like values while the valuation mission is unmerged.
- Multiple audit/outbox implementations make evidence lineage ambiguous.
- Several sibling mission branches independently modify shared trading models, settings, URLs, and migrations; their combined dependency graph has not been certified.
