# Beyvra PAPER/LIVE API migration authority

The revised 2026 PAPER/LIVE mission supersedes the separate Demo API freeze.
PAPER and LIVE are account execution modes, with shared orders, executions,
positions, portfolio, and realtime contracts. PAPER funds never enter the live
financial ledger. A customer cannot promote a PAPER account to LIVE.

`contracts/openapi/beyvra-v1.yaml` remains the checked-in runtime snapshot during
B00. The requested OpenAPI 3.1, AsyncAPI 3.0, and design-notes files were not
provided in either repository or the workspace. Any reconstructed contract must
identify the written mission as its source and must not be represented as an
uploaded original.

The obsolete `codestra-demo-v1.yaml` duplicate has been retired. Its historical
payment/wallet entries are not authority to enable or delete funding handlers.
Legacy funding routes retain their existing removal-after-migration policy.

B00 removes the Demo routes and guest-session creation, adds PAPER/LIVE account
identity with isolated virtual projections, and migrates frontend callers in a
paired B00 branch. Contract reconstruction, the implementation matrix, and
remaining B00 checks must be completed before this milestone is merge-ready.

An API operation is not implemented merely because it appears in a schema.
Provider-dependent operations may be marked implemented and gated only when the
adapter and failure paths are implemented and verified. B19 must prove complete
operation-to-route-to-service-to-test coverage before backend certification.
