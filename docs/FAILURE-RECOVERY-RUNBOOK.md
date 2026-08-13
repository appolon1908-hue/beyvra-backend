# Simulated Trading Failure/Recovery Runbook

## Isolated certification

1. Confirm Docker is local and no staging environment variables are present.
2. Run `./chaos/bin/chaos-harness certify`.
3. Preserve test output and the reconciliation JSON.
4. Confirm `NETWORK_RULES_REMAINING=0` and that Compose removed containers/volumes.

## Recovery and rollback

Outbox claims recover after lease expiry; JetStream deliveries are ACKed only after
the database commit; processed-event uniqueness makes replay safe. Database failures
must roll back the whole transaction. Realtime clients detect a sequence gap, fetch
the canonical order/position snapshot, replace local projections, and resume from
the new cursor. Redis failures return safe retryable errors.

Network partitions are limited to four approved internal pairs. The helper installs
an EXIT/INT/TERM trap and reconnects before reporting success. If cleanup is
interrupted, run `./chaos/bin/chaos-harness down` and inspect the Docker network.

Never point this runbook at staging without a separate approval. Never supply
production or Financial Service credentials. Never enable real trading, external
execution, or real money. A failed invariant blocks promotion; rollback is teardown
of the disposable stack, not mutation of business data.
