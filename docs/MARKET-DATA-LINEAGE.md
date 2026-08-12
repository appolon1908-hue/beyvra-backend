# Market-Data Lineage and Corrections

Every accepted provider event becomes a `MarketDataObservation`. The record contains canonical instrument UUID, source provider, provider symbol, provider event ID, data type, observation and receipt timestamps, the exact effective mapping used, a SHA-256 payload hash, and a bounded safe normalized payload.

Corrections are new observations whose `supersedes` field points at the prior observation. The original is retained. Consumers choose the newest correction chain member; they must never update the original row.

Provider credentials, request headers, raw transport errors, customer data, and unbounded raw payloads are prohibited from `payload_safe`, audit metadata, metrics, and API responses.

Reconciliation checks provider-mapping overlaps, current instrument versions, mapping/instrument consistency, missing hashes, and missing audit evidence. It is read-only:

```bash
python manage.py reconcile_reference_data --json
```

A failed reconciliation blocks readiness but performs no repair.
