# Surveillance Dead Letter

Symptoms: dead-letter counter or poison event. Inspect only the safe error reference and event contract; do not log the raw customer payload. Correct schema/handler defects, replay in isolated mode, then reprocess through the idempotent inbox. Escalate critical trade-event failures. Verify exactly one business effect.
