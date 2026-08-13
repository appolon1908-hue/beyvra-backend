# Institutional Financial Service boundary

The application owns hierarchy and provider-neutral mapping metadata. Financial
Service remains the sole real cash/ledger authority. No direct Financial
PostgreSQL client, SQL, custody mutation, settlement mutation, money movement,
or shadow authoritative cash ledger is introduced. Only opaque future context
(`institution_ref`, `subaccount_ref`, `settlement_ref`) may cross that boundary.
