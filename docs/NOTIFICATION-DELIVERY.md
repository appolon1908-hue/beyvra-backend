# Notification delivery

Evidence states are QUEUED, SENT, DELIVERED, FAILED, BOUNCED, READ. DELIVERED is recorded only when a provider proves it. Transient errors use bounded exponential retry; permanent destination errors go directly to dead letter. Retry exhaustion records a safe reason for operators. Sensitive actions link back to authenticated Beyvra rather than embedding data in email.
