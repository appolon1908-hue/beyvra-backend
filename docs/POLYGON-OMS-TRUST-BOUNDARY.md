# Polygon OMS trust boundary

```text
Frontend -> Beyvra Application Backend -> Financial Service -> Polygon OMS Adapter -> OMS API
```

Financial Service remains authoritative for intent, ledger state,
reconciliation, settlement, and provider-operation state. The application may
call only its existing authenticated Financial Service client. Frontends receive
only canonical Beyvra objects and safe errors.

The application repository contains a transport-free proposal module for
contract tests. It cannot resolve OMS DNS, mint an OMS bearer token, or send an
OMS request. Provider webhooks must terminate at Financial Service after owner
implementation; no application webhook route is registered by this change.

Required invariants:

- direct frontend OMS calls: zero
- direct application OMS mutations: zero
- demo-to-OMS calls: zero
- provider identifiers and errors are not exposed publicly
- Financial PostgreSQL is never accessed by the application
- global financial halt precedes every provider or feature approval
- `POLYGON_OMS_HALTED=true` denies mutations immediately

Only Financial Service may eventually own OMS credentials. Secrets must use its
existing secret-file mechanism; never environment snapshots, logs, fixtures, or
application settings.
