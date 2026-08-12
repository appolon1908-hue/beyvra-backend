# Self-Trade Prevention Failure

Symptoms: STP error alert, crossing same-account orders, or reconciliation violation. Verify surveillance flags, PostgreSQL health, rule version and order/account/instrument scope. Halt simulated order mutation if enforcement is uncertain. Preserve orders, events, audit and logs; never delete evidence. Roll back the candidate or activate the existing trading halt. Escalate to surveillance manager and security. Recovery requires a synthetic self-cross with zero executions and clean reconciliation.
