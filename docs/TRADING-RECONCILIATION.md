# Simulated Trading Reconciliation

`python manage.py reconcile_simulated_trading --format human|json [--tenant ID]`
is read-only. It compares simulation orders, trades/executions, positions,
reservations, projected wallets, outbox, processed inbox events, settlements, and
audit events. JSON is the machine-readable report; human output is `KEY=VALUE`.

The invariant library checks zero lost committed orders/events, duplicate orders,
trades and settlements, overfills, reservation leaks, negative balances, position
accounting errors, cross-tenant successes, invalid states, and missing audit events.
Any nonzero finding exits unsuccessfully; otherwise `RECONCILIATION=PASS`.

The command performs no updates, repairs, publishing, or external calls. Operators
must investigate a failed report and use the normal application recovery path.
