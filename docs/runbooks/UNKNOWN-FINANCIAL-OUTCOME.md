# Unknown financial outcome

1. Halt automatic retry of the mutation. Preserve the original tenant,
   correlation ID, reference, and idempotency key in protected incident
   evidence; do not copy secrets or raw provider responses.
2. Query the canonical Financial Service operation-lookup endpoint using the
   original reference/key. If the versioned contract is unavailable, keep the
   incident unresolved and block readiness. Never substitute application rows
   or provider state as financial authority.
3. If Financial Service proves the operation committed, reconcile projection,
   inbox, outbox, and audit evidence without posting a second mutation.
4. If it proves the operation did not commit, a separately approved workflow
   may decide whether the same idempotency key can be retried.
5. Escalate ambiguity, duplicate evidence, or disagreement. Do not repair the
   ledger automatically.

Current v1 has no authoritative operation lookup. Therefore the tested action
is `CONTRACT_UNAVAILABLE`, no retry, and an open incident pending the Financial
Service owner.

Mark the operation unknown, stop automatic retry, record an incident, and query Financial Service by idempotency key/reference. Reconcile before deciding whether a new mutation is safe. Never present unknown as successful.
