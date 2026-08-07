# P0 retention and data-class inventory

| Data | Class | Minimum handling rule |
|---|---|---|
| Orders and trades | APPLICATION, FINANCIAL_REFERENCE | Immutable identifiers and event history; retention follows trading/legal policy. No authoritative balance fields. |
| Application audit | APPLICATION, PII | Append-only, access-controlled, integrity-hashed before/after values. |
| Sessions/auth challenges | PII, SECRET | Short TTL; hashes instead of reusable credentials; purge after expiry. |
| KYC profiles/files | KYC, PII | Restricted storage and access; never copied into generic event payloads or logs. |
| Market candles/quotes | APPLICATION | Provider-license retention; normalized data only. |
| Provider payloads | APPLICATION | Store only bounded normalized projections; no unrestricted raw payload retention. |
| Webhook payloads | APPLICATION, PII, FINANCIAL_REFERENCE | Encrypt sensitive fields, bounded retention, deduplicate by provider event ID. |
| Notifications | APPLICATION, PII | Default 90-day retention; no secrets or full provider articles. |
| Celery/task results | APPLICATION | No credentials/PII in results; bounded operational retention. |
| Realtime events | APPLICATION, FINANCIAL_REFERENCE | Bounded JetStream/history TTL; standard envelope; no secrets. |
| Financial references | FINANCIAL_REFERENCE | IDs and projections only. Authoritative ledger/balances stay in Financial Service. |
| API/provider credentials, private keys | SECRET | Secret files/approved secret manager only; never ordinary application tables. |

KYC documents, cryptographic private keys, provider credentials, and Financial PostgreSQL credentials are explicitly outside the application event/outbox payload boundary.
