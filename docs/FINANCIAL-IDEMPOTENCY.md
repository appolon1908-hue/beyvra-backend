# Financial idempotency and event delivery

Keys are scoped by tenant, actor, method and canonical endpoint; canonical request hashes detect key reuse with a different payload. Financial Service remains authority for reservation/settlement idempotency. Application intents and events use transactional uniqueness.

Every inbound envelope contains `event_id`, `event_type`, `schema_version`, `occurred_at`, `correlation_id`, `causation_id`, `tenant_ref`, and payload. `financial_inbox` makes duplicate consumption one-effect. Publication coupled to a domain mutation uses the transactional outbox. Poison events enter `financial_dead_letters`; they are never silently dropped. Subjects contain no PII.

Event types must be versioned (`financial.<domain>.<event>.vN`), and the suffix
must agree with `schema_version`. Payloads are canonicalized before hashing and
reject secret-bearing fields. Tenant, type, and payload hash are bound to the
globally unique `event_id`; reuse with different content raises
`EventReplayConflict`, never a duplicate success.

The inbox receipt and handler effects commit in one PostgreSQL transaction.
Failure before commit leaves no receipt and is safe to redeliver. Redelivery
after commit/ACK loss observes the receipt and performs no effect. Tests deliver
the same envelope 100 times concurrently and require one receipt and one effect.

Application financial intent publication uses `financial_outbox`. Domain state
and outbox creation must share `transaction.atomic()`; enqueue rejects calls
outside a transaction. Publishers claim bounded batches with PostgreSQL row
locks and expiring leases. A publisher crash leaves the row durable, and an
expired lease returns it to `PENDING`. Delivery remains at-least-once, so every
consumer still deduplicates by `event_id`.

No publisher, broker, Financial Service, custody, or payment connection is
activated by this implementation.

The Financial Service client emits bounded-label request, failure, duration,
idempotency-conflict, and unknown-outcome metrics. Labels contain only finite
method/outcome/category enums—never URL paths, tenant/user/account references,
idempotency keys, request IDs, or provider details.
