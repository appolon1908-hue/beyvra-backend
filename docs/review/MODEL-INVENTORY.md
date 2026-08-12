# Model inventory

The checked-out backend defines 115 Django model classes. High-authority groups are:

| Concept | Implementations | Initial classification |
|---|---|---|
| Order | `apps.trading.TradingOrder`, legacy `trade.Trade`, provider order APIs | CONFLICT |
| Trade/execution | `trade.Trade`, `reporting.Trade`, `apps.trading.RiskDecision` plus mission-branch execution models | CONFLICT |
| Asset/instrument | `trade.Asset`, `portfolio.Asset`, `real_wallet.Asset`, mission-branch reference-data models | CONFLICT |
| Balance | `wallet.Wallet.balance`, `portfolio.AssetBalance`, `real_wallet.AssetBalance`, Financial Service ledger projection | CONFLICT |
| Ledger | `integrations.DemoLedgerEntry`, `trade.DemoLedgerEntry`, `real_wallet.Ledger*`, Financial Service ledger | CONFLICT |
| Idempotency | `foundation.IdempotencyRecord`, `real_wallet.IdempotencyRecord`, Financial Service ledger claims | STRUCTURAL DUPLICATE |
| Outbox | `foundation.OutboxEvent`, `trade.DemoEventOutbox`, `real_wallet.OutboxEvent`, email outbox, Financial Service outbox | STRUCTURAL DUPLICATE |
| Audit | foundation, integration, real-wallet, provider-governance and Financial Service audit records | AMBIGUOUS |
| Webhook | notification and real-wallet subscriptions/deliveries plus provider/Financial Service inboxes | STRUCTURAL DUPLICATE |

The application backend has no Financial PostgreSQL model or database alias. The `real_wallet` ledger is nevertheless a dormant application-owned shadow real-money implementation and is not canonical.

