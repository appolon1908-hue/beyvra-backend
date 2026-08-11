# Unknown Execution Outcomes

An ambiguous post-send timeout creates canonical `UNKNOWN` execution and an unresolved outcome. It forbids retry and failover.

Resolution order is provider-order lookup, client/idempotency lookup, execution-report inspection, then inbox reconciliation. The recovery service accepts evidence only from its trusted lookup callback. The operator API rejects caller-supplied evidence with `PROVIDER_LOOKUP_REQUIRED`; it cannot force success. Unresolved records remain critical reconciliation findings.
