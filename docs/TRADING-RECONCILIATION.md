# Simulated Trading Reconciliation

`python manage.py run_reconciliation --scope full|orders|settlements|positions|outbox --format human|json [--tenant ID]`
is read-only. It compares simulation orders, trades/executions, positions,
reservations, projected wallets, outbox, processed inbox events, settlements, and
audit events. JSON is the machine-readable report; human output is `KEY=VALUE`.

The invariant library checks zero lost committed orders/events, duplicate orders,
trades and settlements, overfills, reservation leaks, negative balances, position
accounting errors, cross-tenant successes, invalid states, and missing audit events.
Any nonzero finding exits unsuccessfully; otherwise `RECONCILIATION=PASS`.

The business scan is read-only and has no repair path. By default it appends an
immutable run and hashed violation evidence record; `--no-persist` suppresses evidence
storage for local diagnostics. Output contains run/started/completed timestamps,
status, checks and opaque violations. PostgreSQL triggers reject mutation/deletion
after completion. Operators must preserve the run ID and investigate; automatic
repair, publishing and external calls are prohibited.
