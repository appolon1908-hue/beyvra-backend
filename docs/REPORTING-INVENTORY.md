# Reporting inventory

Legacy `reporting.Transaction`, `Trade`, and file-path `Report` are non-authoritative. Wallet and trade apps contain product records; real financial statements must come from Financial Service and are not enabled here. `TransactionHistoryEntry` is the normalized simulation projection using decimal fields, stable ordering, source reference, version, and explicit simulation label.

Canonical activity, trade, fee, and transaction reads are `/api/v1/reports/*`. Large exports use idempotent private `ReportJob` records. CSV output neutralizes `=`, `+`, `-`, and `@` formula prefixes.
