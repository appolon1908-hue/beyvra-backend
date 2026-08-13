# Compliance certification evidence

Certification scope is the isolated readiness branches and PostgreSQL 16 test database. Financial PostgreSQL and production were not accessed or changed. Real trading, live trading, external execution, real money, deposits, withdrawals, and internal transfers are hard-disabled in settings.

| Phases | Authority and evidence | Status |
|---|---|---|
| 1–7 | Inventory; explicit account/KYC/AML/sanctions/jurisdiction enums; persisted profiles and restrictions | PASS |
| 8–11 | One policy engine for trading/deposit/withdrawal/transfer; stable reasons and policy version; server order gate | PASS |
| 12–16 | Safe profile/requirements/session APIs; provider-neutral interface and disabled-by-default governance | PASS |
| 17–23 | Cases, allow-listed append-only events, scoped workflow, maker/checker overrides, expiry and review-date fail-closed checks | PASS |
| 24–28 | PII boundary, opaque references, truthful encryption statement, immutable audit/decision evidence and order snapshots | PASS |
| 29–33 | Private user-scoped realtime events, safe frontend states/errors, simulated order compliance gate, hard real-value denial | PASS |
| 34–39 | Inbox idempotency, event-ID-bound HMAC, shared transactional outbox, PostgreSQL concurrency, tenant and role isolation | PASS |
| 40–42 | PostgreSQL migrations, zero/rollback/reapply/drift certification, versioned policy | PASS |
| 43–46 | Bounded metrics, alerts, eight-panel no-PII dashboard, invariant reconciliation | PASS |
| 47–54 | Retention hold, provider failure and stale-result handling, sanctions/jurisdiction fail-closed, security/privacy fixtures | PASS |
| 55 | External provider staging test; approvals and credentials absent | NOT_AUTHORIZED |
| 56–57 | Full backend, focused compliance/trading, frontend unit/component, typecheck, lint, and build | PASS |
| 58–59 | Deployed staging E2E; bounded synthetic probe found the legacy real-wallet compliance routes, not this branch | BLOCKED_NOT_DEPLOYED |
| 60 | Current-source secret scan, dependency/source/container critical scan, SBOM generation | PASS |
| 61–63 | Required documents/runbooks, isolated branches, commits, pushes, and draft PRs | PASS |

The test suite uses synthetic `example.test` identities and opaque fixture references. It never asserts that a real person passed KYC, AML, sanctions, or jurisdiction screening. Provider fixtures cover approved, rejected, review, expired, possible sanctions match, unavailable provider, invalid signature, delivery replay, conflicting replay, and stale provider result.

## Certified command results

- Full backend on the final tree: 218 tests passed on PostgreSQL 16.14.
- Final focused authority suite: 57 tests passed (33 compliance, 21 canonical trading, and 3 realtime V2 contract tests).
- Frontend: 106 unit/component tests passed; typecheck, lint, safe-error checks, localization checks, and production build passed.
- PostgreSQL: migrate from zero, system check, migration drift none, rollback, and reapply passed through migration `canonical_compliance.0014`.
- Reconciliation: blocked-compliance allowed decisions `0`, restricted-account allowed trades `0`, missing audit events `0`.
- Security: current-source secrets `0`, critical source/container findings `0`, production npm vulnerabilities `0`, CycloneDX SBOM generated.

This file deliberately distinguishes completed local certification from unexecuted external staging evidence. It must not be used to infer provider, production, or real-money approval.

## Staging probe

The configured `https://staging.beyvra.com` target was probed with a disposable synthetic guest session and no PII. The no-slash canonical compliance paths redirected to the legacy trailing-slash real-wallet handlers, which returned `FEATURE_DISABLED`; the deployed simulated-order contract also differed from this branch. Therefore staging does not contain the draft implementation and cannot certify its eligible/restricted/KYC-pending/AML-blocked matrix. The temporary guest credential was removed after the probe. No provider call or real financial effect occurred.
