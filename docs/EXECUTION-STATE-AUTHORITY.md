# Execution State Authority

Canonical states are `CREATED`, `SUBMITTING`, `SUBMITTED`, `ACKNOWLEDGED`, `WORKING`, `PARTIALLY_FILLED`, `FILLED`, `CANCEL_PENDING`, `CANCELLED`, `REJECTED`, `EXPIRED`, and `UNKNOWN`. Row locks and an explicit transition matrix reject terminal regressions and increment a version on every transition.
