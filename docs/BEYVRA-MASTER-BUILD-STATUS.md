# Beyvra PAPER/LIVE master build

The revised written mission is the implementation authority. Execute backend
B00–B19, frontend F00–F15, cleanup and integrated certification. Each milestone
requires a tested branch, push, PR, green required checks, review, merge and main
synchronization. The platform mission is not complete or production-certified.

## B00 — API Contract Migration: validation and review

Baseline: backend `688d6b1`, frontend `46472a1e780f20c531297c74b1ab603156abea93`.
No repository AGENTS.md was present in these checkouts. The original named
attachments were unavailable. The user subsequently instructed implementation to
continue by extending the repositories; the written mission and existing runtime
are used with explicit provenance, not represented as uploaded originals.

### Implemented on the coordinated branches

- TradingAccount stores PAPER/LIVE identity separately from virtual projections.
  PostgreSQL constraints reject PAPER financial permissions and LIVE ownership
  of virtual balances. The identity trigger prevents mode/ownership conversion;
  new LIVE records must start PENDING with effects disabled.
- Migrations 0010/0011 preserve virtual IDs, owners, restrictions and funds during
  backfill and preserve the projection on reversal. Account restrictions feed
  existing risk validation; lookup never reactivates a restricted identity.
- Runtime Demo routes, guest-session creation and unused guest/configuration
  views are removed. Existing session readers remain during caller migration.
- Runtime schema generation now uses OpenAPI 3.1, Beyvra identity and explicit
  account response fields. The primary snapshot is
  `contracts/openapi/beyvra-openapi-3.1.yaml`. The old primary filename and duplicate
  tracked FX snapshot are removed. CI may generate an ignored temporary snapshot.
- Regeneration captures 21 routes already present in code but missing from the
  previous snapshot. Watchlist handler operation IDs match their maintained
  contract. The owned treasury contract now has its 37 missing IDs; invalid
  operation references and malformed response descriptions are repaired. The
  upstream Financial Service snapshot keeps its original bytes and SHA pin;
  its 18 operations without IDs are validated as a dependency, not renamed by
  this consumer or counted as owned platform operations.
- Validation rejects missing/duplicate/retired IDs, duplicate YAML keys, broken
  local references, retired tags/paths, provider customer URLs and direct wallet
  mutation paths. Contract CI also runs full OpenAPI semantic validation.
- AsyncAPI 3.0 declares all thirteen target channel families, typed payloads,
  server authorization metadata and REST recovery. Design notes preserve account,
  money, provider, AI, communications and observability boundaries. These target
  declarations do not claim B17 runtime implementation.
- The implementation matrix is generated from every discovered operation ID,
  normalizes server base paths, and de-duplicates equivalent snapshots. Eight
  existing watchlist operations have reviewed backend source/test bindings.
  Missing evidence remains visibly unassigned; certification rejects missing
  evidence, changed source bindings, missing IDs and unsupported gate claims.
- Workspace bootstrap is moved from the retired trade/demo_engine.py module to
  apps.workspace.bootstrap, preserving the existing handler rather than creating
  another authority. Fixed-Time presentation defaults remain separately named.
- Frontend application callers and E2E/load fixtures no longer call Demo APIs.
  Test setup accepts normally authenticated PAPER session state and uses BFF CSRF;
  it never manufactures readable bearer cookies. The old fixed-time trade test is
  removed and idempotency conflict coverage extends the existing trading suite.
- The load harness uses the existing V2 authorization endpoints and /ws/v2/ only.
  It counts confirmed connections/subscriptions and fails on rejected or missing
  acknowledgments. Isolated protocol tests do not claim live load certification.
- Repeated database testing exposed migration-seed dependence in trading tests.
  Those tests now declare their settlement-calendar fixture. A regression proves
  a genuinely missing calendar rolls back fills and preserves reservations.
- The staging API certifier requires `BEYVRA_STAGING_ACCESS_TOKEN` for a dedicated
  identity provisioned through normal sign-in. Missing credentials fail before
  requests or evidence generation; the retired session-creation fallback is gone.
  Two isolated regressions cover this boundary without contacting staging.

### Validation and release evidence

Backend commit 19781b3 passed all eleven GitHub checks and received an independent
approval. Later changes require their own final-head CI and review; those older
results do not certify the current working branch.

The expanded local PostgreSQL suite passes all 116 tests, including the missing-
calendar rollback regression. Fifteen OpenAPI, eleven matrix and ten AsyncAPI
regressions accompany full semantic validation of all six current documents.
The five Financial Service consumer-contract tests additionally enforce the
unchanged upstream snapshot, scopes, absent owner operations and fixture shapes. Frontend build/typecheck pass;
lint has one pre-existing requireAuth hook warning and no errors. Ten session
preflight tests, three isolated V2 protocol tests and seven public browser tests
pass. Full authenticated staging E2E, final load, financial/provider certification,
image publication and production rollout are not established by these checks.

### Remaining milestone/release work

1. Complete final-head checks and review the paired B00 PRs before merging either
   coordinated migration and advancing to B01.
2. Keep expanding the existing services and canonical contract in the prescribed
   milestones. The runtime snapshot is not a claim that every final target route
   or provider adapter is present. Complete all matrix bindings by B19.
3. Supply normal authenticated PAPER fixtures in the integrated staging workload
   and execute the authenticated suite before final release certification. Test
   listing, mocked protocol tests and public-only checks are not substitutes.
4. Record exact source SHAs, immutable image digests, migrations, recovery and
   staging evidence before production deployment. Preserve protected approvals.

### Preserved boundaries

SimulatedAccount is an internal virtual projection, not a second public account
identity. The compatibility simulation header and /api/v1/trading/* still need
account-selected /orders, /executions and /positions migration in B06/B12. Existing
realtime token endpoints/channel aliases remain B17/F13 migration work. UI
Fixed-Time labels and legacy display types remain F01/F05 cleanup work.

Legacy payment, wallet and provider-specific compatibility routes retain their
removal-after-caller-migration policy. No production credentials, financial
activation flags or protected release controls have been changed. Main requires
independent approval and green required checks; an author's approval cannot
replace another review or bypass protection.
