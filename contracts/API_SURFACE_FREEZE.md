# Beyvra PAPER/LIVE API migration authority

The revised written PAPER/LIVE mission governs this migration. Accounts determine
execution mode. PAPER and LIVE share the target order, execution, position,
portfolio and realtime surfaces. PAPER funds never enter the real ledger and a
customer cannot promote a PAPER account to LIVE.

`contracts/openapi/beyvra-openapi-3.1.yaml` is the generated runtime snapshot. It
extends the existing Django schema with OpenAPI 3.1 and explicit account identity.
It records its provenance and is not presented as an unavailable uploaded
original or as evidence that every final target API already exists. Auxiliary
domain contracts remain checked; duplicate tracked runtime snapshots are removed.

The retired Demo namespace/tag/operation IDs cannot be reintroduced. The old Demo
specification is removed. Legacy funding routes are removed after callers migrate;
their presence never grants permission to enable funding or external execution.

`docs/API-IMPLEMENTATION-MATRIX.md` is generated from operation IDs. Verified
backend implementations have source-bound evidence; unverified rows have no
assigned status. Final certification rejects missing evidence. Returning a generic
response or FEATURE_DISABLED does not establish an implemented provider adapter.

B00 establishes this migration foundation and its paired caller/test-harness
changes. The subsequent milestones extend the existing services, reconcile target
paths, add provider integrations and finish frontend wiring. B19 and final staging
certification must prove complete coverage before production release.
