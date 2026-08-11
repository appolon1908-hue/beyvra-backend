# Webhook standards

Every provider webhook must validate an allowlisted route, signature over original bytes, timestamp tolerance when supported, content type, and bounded body size. Event identity is reserved transactionally in an inbox before business effect. One hundred duplicates produce one effect.

Handlers write business state and transactional outbox atomically. Retryable failures use bounded backoff; exhausted events enter a dead letter queue with alerting and auditable replay. Secrets, raw credentials, and unsafe provider errors never appear in responses or logs.

