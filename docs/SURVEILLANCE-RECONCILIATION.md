# Surveillance Reconciliation

`python manage.py reconcile_surveillance` is read-only. It detects restricted accepted orders, critical events without cases, cases without events, missing surveillance audit and missing outbox records. It never repairs orders, restrictions, evidence or audit automatically.
