# Financial Service outage

Keep all mutations disabled. Confirm health without exposing endpoints, watch the bounded circuit breaker, suppress retry storms, and retain intent/outbox evidence. Demo readiness may remain healthy. Recovery requires closed breaker and reconciliation; do not replay mutations blindly.
