# Reporting inventory

Legacy `reporting.Transaction`, `Trade`, and file-path `Report` are non-authoritative. Wallet and trade apps contain product records; real financial statements must come from Financial Service and are not enabled here. `TransactionHistoryEntry` is the normalized simulation projection using decimal fields, stable ordering, source reference, version, and explicit simulation label.

Canonical activity, trade, fee, and transaction reads are `/api/v1/reports/*`; trade and fee routes enforce their canonical entry types. Large exports use idempotent private `ReportJob` records and run asynchronously only after operational reconciliation passes. CSV output neutralizes `=`, `+`, `-`, and `@` formula prefixes. Artifact references are never serialized; owner-scoped downloads require a completed, unexpired, reconciled job and create an audit event.

The default artifact adapter writes opaque UUID-named files beneath `OPERATIONS_PRIVATE_ARTIFACT_ROOT` with private directory/file modes. Staging must mount that path as private storage shared by API and worker processes. Public object storage is not supported by this adapter.
