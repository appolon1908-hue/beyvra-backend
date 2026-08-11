# Treasury / Financial Service Boundary

```text
Frontend -> Beyvra /api/v1 and /ws/v2 -> Treasury simulation/read models
                                           X Financial PostgreSQL
                                           X bank/custody/broker transfer APIs
Future read-only contract -> Financial Service -> Financial PostgreSQL
```

Financial Service is the future real-balance, reservation, transfer, settlement, and ledger authority. This app has no Financial database settings, SQL, credential, or mutation client. All real-value flags are hard false.
