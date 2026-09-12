# Beyvra PAPER/LIVE master build

The revised 2026 mission supersedes the separate Demo/Live design. Execute
backend B00–B19, frontend F00–F15, final cleanup, then integrated certification.
Each milestone requires a tested branch, push, PR, green required checks,
review, merge and main synchronization. This mission is not complete.

## B00 — API Contract Migration: in progress

Baseline: backend `688d6b1`, frontend `46472a1e780f20c531297c74b1ab603156abea93`.
No repository `AGENTS.md` was found in either fresh checkout.

The named `beyvra-openapi-3.1.yaml`, `beyvra-asyncapi-3.0.yaml`, and
`beyvra-api-design-notes.md` were not found in the workspace or either repository.
Work continues from the user's written specification. Reconstructed files must
identify that provenance; they must not be described as uploaded originals.

### Implemented on the B00 branches

- Contract validation rejects duplicate operation IDs, broken local references,
  duplicate YAML keys, retired Demo paths/tags, named provider customer paths,
  and direct wallet balance/credit mutation routes. External references fail
  explicitly; the checker does not claim full OpenAPI semantic validation.
- The protected CI workflow is unchanged. A separate read-only workflow runs
  contract regression tests and lint. No trust pins or protection rules changed.
- `TradingAccount` now stores PAPER/LIVE identity separately from virtual balance
  projections. PostgreSQL constraints prevent PAPER funding/withdrawals and LIVE
  ownership of a paper projection. A trigger prevents execution-mode conversion
  and identity reassignment. New LIVE records must begin PENDING with effects off.
- Migration `0010` backfills existing virtual accounts as PAPER while retaining
  IDs, ownership, currency, restrictions, timestamps and virtual funds. Migration
  `0011` installs the identity boundary. Reverse migration retains virtual funds.
- Existing account lookup and serialization use the new identity; account state
  and trading permission participate in risk evaluation. Identity lookup does not
  reactivate restricted accounts. Lock ordering remains projection then identity.
- Runtime `/api/v1/demo/*` routes and guest-session creation routes are removed.
  Unreferenced guest-session and Demo-configuration views are removed. The existing
  session reader still supports already-issued identities during migration.
- Active OpenAPI snapshots no longer advertise the removed routes. The duplicate
  `codestra-demo-v1.yaml` contract is retired; historical funding entries in that
  snapshot were not authorization to enable or delete funding handlers.
- The paired frontend B00 branch removes application Demo API clients. Practice
  entry redirects through secure login, platform flags use workspace bootstrap,
  and PAPER accounts cannot enable financial UI capabilities.

These changes are not deployed. The two B00 branches form a coordinated migration,
not the start of a later frontend milestone. Frontend application callers must be
merged and released before backend route retirement reaches a running workload.

### Current validation evidence

- The initial preparatory head `558bb9c` passed all six GitHub checks, including
  application validation and container scans. Those results do not certify later
  commits; each new head requires fresh CI.
- Twelve contract regression tests pass against seven current documents.
- PostgreSQL account, retirement and full canonical trading regression run:
  109 tests passed after lock-order and timestamp-preservation refinements.
- Frontend dependency installation, build and typecheck pass. Lint has no errors
  and one existing `requireAuth` hook-dependency warning. Five targeted client and
  capability tests pass. This does not establish full E2E certification.

### Remaining B00 work

1. Finish reconstructing and validating the OpenAPI 3.1, AsyncAPI 3.0 and design
   notes from the written specification, and reconcile all contract operations.
2. Generate the implementation matrix from operation IDs with evidence-backed
   service, authorization, feature-gate, test and frontend-caller mappings. Never
   label an unimplemented provider adapter as implemented and gated.
3. Finish the paired frontend test-harness migration: older E2E/load fixtures still
   reference retired guest/Demo routes and require authenticated PAPER fixtures.
4. Update remaining inventories and schema account definitions, validate migration
   compatibility and all required CI checks, and review the final milestone diff.
5. Complete the coordinated B00 PR reviews and merges before starting B01.

### Preserved boundaries and limitations

`SimulatedAccount` remains the internal virtual projection during engine migration;
it is not a second public trading account model. The legacy simulation header and
`/api/v1/trading/*` compatibility contract still require migration to the final
account-selected `/orders`, `/executions`, and `/positions` contract. B06 must finish
PAPER execution behind that common surface; B12 must finish governed LIVE routing.

Legacy `/api/payment/**`, wallet mutations and other provider-specific compatibility
surfaces retain their removal-after-migration policy. No provider credentials,
production deployment or live financial activation was changed.

Backend main currently requires an independent approving review and green
`container`, `exact-head-base-ci`, `secrets`, `validate`, and `orchestrator-contract`
checks with current main ancestry. GitHub does not count an author's self-approval
as that required review. Recheck protection on the final PR head; do not bypass it.
