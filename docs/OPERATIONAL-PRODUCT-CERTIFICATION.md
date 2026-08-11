# Operational product certification

## Recorded starting state

| Repository | Candidate | Branch | Starting head | Remote | Starting worktree |
|---|---|---|---|---|---|
| Backend | `/root/backend` | `feat/compliance-account-state-readiness` | `ccea9c783f5f497f125bf6b412ced5a6ce4537a6` | `https://github.com/appolon1908-hue/backend.git` | clean |
| Frontend | `/root/front` | `feat/compliance-account-state-readiness` | `d6c9279982c39c722791965c8aa4490fa76b1316` | `https://bitbucket.org/tradx2025/front.git` | pre-existing compliance changes preserved |
| Financial Service | `/root/github-projects/codestra-financial-service` | `feat/financial-boundary-foundation` | `e27b9f67efca3dde5cb295712cb556133e4c00b3` | `https://github.com/Codestra-SRL/codestra-financial-service.git` | read only |

Mission worktrees are `/root/beyvra-operational-backend` and `/root/beyvra-operational-frontend`. The observed staging images were backend `beyvra-backend-staging:b07a04fdde91b9c5eb6e3f12a80e212bd30aa305` (`sha256:e2a83547...`) and frontend `beyvra-frontend-staging:d6c9279982c39c722791965c8aa4490fa76b1316` (`sha256:a0497dd2...`). No staging domain was established and no deployment was attempted. The backup is `/root/backups/beyvra-operational-product-readiness-20260811T081826Z/`, with git bundles and SHA256 manifest. `BACKUP=PASS`; `ROLLBACK_AVAILABLE=YES`.

## Safety state

All seven real-feature flags are hard-coded false in backend authority. Support impersonation is false. No custody, payment, or execution provider was activated. Financial Service and production were not changed.

## Certification evidence

- Python 3.11.15 and PostgreSQL 16.14: migration from zero, operations rollback, reapply, drift check, and system check pass. The current PostgreSQL scoped suite has 28 passing tests, including direct bulk-update/delete attempts against the audit trigger; the corresponding SQLite suite passes with the PostgreSQL-only trigger assertion skipped.
- Internal operator APIs now cover scoped fraud cases, support escalation/internal notes, legal hold creation, action requests/independent approval, audit timeline, and non-destructive reconciliation. Cross-tenant account targets are rejected before freeze or hold creation.
- Notification delivery has a fail-closed provider interface. No delivery provider is configured or activated, and provider-disabled outcomes are never represented as delivered. `/ws/v2/` rejects anonymous clients and isolates authenticated connections by tenant/account-derived private groups; the scoped suite includes cross-tenant realtime isolation coverage.
- Audit events, security events, support timeline events, transaction history, and issued statements reject application updates/deletes and are protected by PostgreSQL `BEFORE UPDATE OR DELETE` triggers. Operator action requests retain only the governed state-machine mutability required for approval and execution.
- Frontend TypeScript, ESLint, and production Vite build pass. The operational center is responsive at CSS breakpoints and uses semantic headings, status/alert regions, keyboard-focus styling, and scrollable table labeling.
- Gitleaks reports zero current-source leaks after moving the legacy demo provider key to environment configuration. Frontend production dependency audit reports zero vulnerabilities.
- Trivy filesystem scan reports zero critical source/dependency/misconfiguration findings. The refreshed Debian 13 image reports zero **fixable** critical findings; 17 upstream Debian critical advisories remain unfixed/fix-deferred and require base-image vendor resolution. The CycloneDX SBOM is stored with the backup.
- The full legacy backend suite discovers 61 tests but is not green due to pre-existing wallet fixture/schema drift, auth throttle/test isolation, reporting date fixtures, and stale serializer expectations. The new domain's PostgreSQL suite is green; this document does not claim the legacy suite passes.

## External gates

Legal/Compliance must set retention periods, deletion constraints, residency conclusions, processor/DPA approvals, and mandatory-notification policy. Independent Security must review operator RBAC/maker-checker and the legacy broad admin endpoints. Protected repository owners must review/merge. Staging deployment/E2E awaits a discoverable isolated staging target and policy approval.
