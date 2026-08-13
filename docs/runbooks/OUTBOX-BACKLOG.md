# Outbox Backlog

Symptoms: pending count/age rises or publisher heartbeat is stale. Dashboard: Trading Pipeline. Alert: BeyvraOutboxBacklogCritical. Verify NATS, publisher, DB, and oldest event without printing payloads. Restart only the simulation publisher; replay relies on event IDs. Roll back recent worker-only change if implicated. Escalate to trading/platform. Confirm backlog drains, publication resumes, and duplicate effects stay zero.

Pause optional producers if required, recover the publisher, and prove zero lost events or duplicate business effects.
