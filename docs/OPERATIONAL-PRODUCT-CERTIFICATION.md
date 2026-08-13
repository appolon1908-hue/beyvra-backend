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

- Python 3.11.15 and PostgreSQL 16: migration from zero, rollback of the latest operations migration, reapply, drift check, and system check pass. The current PostgreSQL operations suite has 51 passing tests, including direct bulk-update/delete attempts against immutable-record triggers; the corresponding SQLite suite passes with the PostgreSQL-only trigger assertion skipped.
- Internal operator APIs cover scoped fraud cases, support escalation/internal notes, masked account summaries, compliance and simulation-only financial views, legal hold creation/release, emergency trading halt/release, action requests/independent approval, role-filtered audit timeline, provider/feature state, incidents, and non-destructive six-domain reconciliation. Cross-tenant account targets are rejected before freeze or hold creation.
- Notification delivery has a fail-closed provider interface. No delivery provider is configured or activated, and provider-disabled outcomes are never represented as delivered. `/ws/v2/` rejects anonymous clients and isolates authenticated connections by tenant/account-derived private groups; the scoped suite includes cross-tenant realtime isolation coverage.
- Audit events, security events, support timeline events, transaction history, issued statements, and trade confirmations reject application updates/deletes and are protected by PostgreSQL `BEFORE UPDATE OR DELETE` triggers. Operator action requests retain only the governed state-machine mutability required for approval and execution.
- Newly issued JWTs are bound to canonical account sessions; revoked or expired sessions fail authentication, and privileged users cannot use transitional unbound tokens. Browsers use Secure, HttpOnly, SameSite=Strict access/refresh cookies with CSRF enforcement on unsafe cookie-authenticated requests; readable cookies contain only non-secret session-presence markers. Password and MFA changes revoke sessions and emit safe security notification events. Password-reset requests return the same response for known and unknown email addresses.
- Canonical login risk evaluation now derives failed-login, device, network, credential-change, session, and freeze signals from backend records. Active emergency trading halts and account freezes precede simulated trading authority. Simulation statements require six-domain reconciliation, refuse real financial history, are immutable/versioned, and trade-confirmation reads are owner/tenant scoped.
- Frontend TypeScript, ESLint, and production Vite build pass. The operational center is responsive at CSS breakpoints and uses semantic headings, status/alert regions, keyboard-focus styling, and scrollable table labeling.
- Gitleaks 8.30.1 reports zero current-source leaks. Trivy 0.72.0 filesystem scanning reports zero high/critical dependency findings and zero secret findings. Configuration scanning reports zero high/critical findings after converting the repository Nginx image to the non-root `nginx-unprivileged` runtime. Its review image health endpoint passed on port 8080 while Docker reported runtime UID `101`.
- Fresh backend and Nginx review images both report zero fixable high/critical vulnerabilities under the same `--ignore-unfixed` gate used by CI. The generated CycloneDX SBOM contains 257 components at `docs/sbom/backend-operational-control-plane.cdx.json`.
- The complete backend suite now discovers 123 tests and passes 122 with one PostgreSQL-trigger assertion intentionally skipped under SQLite. The PostgreSQL 16 operations suite independently passes all 51 tests. Artifact-worker storage failures are bounded to three retries and atomically mark jobs `FAILED` rather than leaving them in `RUNNING`.
- Six valid Grafana dashboard definitions and matching Prometheus alert rules cover account security, support operations, reporting, privacy operations, notifications, and operator control. All 18 referenced metric series resolve to declared bounded-label collectors; direct customer, tenant, case, report, notification, and provider identifiers are prohibited as labels.

## Isolated staging-safe E2E

The shared `staging.beyvra.com` deployment is explicitly simulation-only, but its runtime checkout contained unrelated changes and was not overwritten. Instead, the exact review image was exercised through localhost HTTP with `API_ENV=staging`, PostgreSQL 16, Redis 7.4, a real Celery worker, a private shared artifact volume, and synthetic accounts only. The run passed login/new-device creation, bound-session revocation, support case/message/escalation with internal-note isolation, notification read and arbitrary-ID rejection, freeze plus independent unfreeze approval/execution, legal-hold deletion disposition, reconciled CSV export and private download, privacy export and private download, operator audit timeline, all-false safety flags, and denied provider execution.

Post-run ORM evidence reported zero real wallets, real-wallet transactions, payments, withdrawal requests, trades, external outbox events, and executed provider activations. The isolated containers, synthetic PostgreSQL/Redis data, and artifact volume were then deleted so test PII did not persist. The public/shared staging deployment and production were unchanged.

Legacy deposit, withdrawal, internal-transfer, payment-processing, Stripe checkout/webhook, Binance payment, and withdrawal-request mutation routes now fail before validation, local record creation, provider construction, or balance mutation. External broker order routes are not registered unless paper-only, real-trading, external-execution, and real-money authorities all permit them; the current hard-coded authority leaves them absent. Real wallets and their transaction rows are excluded from customer wallet APIs. Full/partial freezes are checked before feature eligibility, including simulated trading mutations.

## External gates

Legal/Compliance must set retention periods, deletion constraints, residency conclusions, processor/DPA approvals, and mandatory-notification policy. Independent Security must review operator RBAC/maker-checker and the legacy broad admin endpoints. Protected repository owners must review/merge. Promotion of the reviewed images to the shared staging domain remains an owner-controlled deployment action.
