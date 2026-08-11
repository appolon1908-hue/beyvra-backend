# Beyvra Webhook Standards

Inbound webhooks use `/api/v1/webhooks/{provider}/{purpose}` or a documented compatibility handler. Provider-specific objects remain inside adapters.

1. Enforce a 256 KiB body bound before parsing.
2. Authenticate provider identity, body integrity, signature, and timestamp before business logic. The generic contract signs `provider.purpose.timestamp.event_id.raw_body` with HMAC-SHA256. Provider-native schemes may replace this only when documented and tested.
3. Accept at most 30 seconds of future clock skew and 300 seconds of age. Event IDs are bounded to 255 safe characters.
4. Store a SHA-256 body hash in a unique provider/purpose/event inbox record. Identical duplicates are acknowledged without a second effect; a changed body returns `WEBHOOK_REPLAY_CONFLICT`.
5. Persist domain mutation, processed inbox marker, audit evidence, and outbox event in one transaction. Never acknowledge a state mutation that can lose its required event.
6. Unknown event types do not mutate domain state. They create an observable dead letter with a non-sensitive error code and return a safe acknowledgement.
7. Transient failures leave retryable inbox/outbox state. Poison events are dead-lettered for operator remediation; raw payloads and PII are not copied into alerts.
8. Secret rotation uses a bounded overlap of explicitly configured old/current secrets. Empty, wildcard, or implicit secrets never authenticate.
9. Metrics use bounded `provider`, `webhook_type`, and `result` labels. Alerts cover signature spikes, dead-letter growth, and processing failures.

The production configuration contains no active generic provider secrets or event types. Compliance has a separately governed, fixture-certified handler. Legacy payment processing is hard-disabled while real money and real deposits are disabled.
