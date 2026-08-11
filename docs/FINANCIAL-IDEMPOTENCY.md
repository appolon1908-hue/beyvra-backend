# Financial idempotency and event delivery

Keys are scoped by tenant, actor, method and canonical endpoint; canonical request hashes detect key reuse with a different payload. Financial Service remains authority for reservation/settlement idempotency. Application intents and events use transactional uniqueness.

Every inbound envelope contains `event_id`, `event_type`, `schema_version`, `occurred_at`, `correlation_id`, `causation_id`, `tenant_ref`, and payload. `financial_inbox` makes duplicate consumption one-effect. Publication coupled to a domain mutation uses the transactional outbox. Poison events enter `financial_dead_letters`; they are never silently dropped. Subjects contain no PII.
