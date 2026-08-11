# Surveillance Consumer Failure

Symptoms: stale heartbeat, consumer lag or missing processed events. Confirm PostgreSQL, NATS/JetStream and outbox health. Restart only the affected consumer; do not purge the stream. Verify inbox idempotency, backlog drain, zero duplicate effects and reconciliation PASS before clearing the incident.
