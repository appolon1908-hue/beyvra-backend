# Migration inventory

The checked-out backend contains 120 Django migration files across 16 application labels. Financial Service uses a separate ordered and hashed SQL migration authority.

The checked-out backend graph is linear per installed application under Django inspection, but the active mission branches are not converged:

- Most trading stacks share `trading.0002_simulated_trading` and then diverge through execution migrations.
- The institutional branch introduces a different `trading.0002` lineage.
- Separate mission stacks independently edit `apps.trading.models` and application registration.
- Ordinary pairwise Git cleanliness does not establish a valid combined Django graph.

Migration-from-zero, PostgreSQL 16 schema comparison, drift, rollback and reapply are certification gates after a combined candidate exists.
