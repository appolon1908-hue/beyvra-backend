# Database change safety

Migrations classify as expand, data migration, contract, index, constraint, type change, backfill, or review required. Destructive/alter/index operations receive lock review. PostgreSQL 16 zero migration, drift, reverse, reapply, and old/new compatibility evidence are required.
