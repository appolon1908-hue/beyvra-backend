# PostgreSQL migration certification

- PostgreSQL: 16
- Migration from zero: PASS
- Django system check: PASS
- Migration drift: NONE
- Rollback: PASS
- Reapply: PASS
- Staging compatibility: PASS

The canonical trading migration uses PostgreSQL `ADD COLUMN IF NOT EXISTS` so a previously deployed simulation column is reconciled without skipping the new eligibility fields. Django state remains explicit and rollback/reapply was certified in a disposable database.
