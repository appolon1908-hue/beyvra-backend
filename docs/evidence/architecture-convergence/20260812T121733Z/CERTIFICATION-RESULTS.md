# Certification results

## Safety

- Real trading, external execution, settlement, deposits, withdrawals and real money remained disabled.
- No production deployment or mutation occurred.
- No live broker/provider or Financial Service mutation request was sent.
- Financial Service source remained unchanged.

## Rollback

Bundles and the pre-existing backend worktree archive are in `/root/backups/beyvra-convergence-20260812T122652Z/`.

| Artifact | SHA256 |
|---|---|
| backend.bundle | `a5bd4d4bd8c74a662b2afd0d98a61d29d8bb6fb7c3a9c53621fe7eea116814e8` |
| frontend.bundle | `223ac925d93173abf5c96b0de3b948ad16b655bafce02f708287470d5bd02655` |
| financial-service.bundle | `6269c0af1c0e267d8f74e2d0c0c4b55acc0dd54245805a5a155b647a6ad0bf21` |
| governance.bundle | `6824fa54f0d4b603de08a3f4bfa09b0253aee30c9c1b18e9e37a31b6512e2ae5` |
| backend-preexisting-worktree.tar.gz | `371fa389138a7157b5f66bfd81bafc8f3154ca1d8fc9ee925c8dc7db42e79163` |

## Tests and contracts

- Backend: PostgreSQL 16 migration-from-zero and 190 tests PASS; test database destroyed afterward.
- Django system check and migration drift: PASS / no changes detected.
- Generated OpenAPI SHA256: `bcc69330308ba79d609e54ac760253d7620bb0a54129c146228b5135203e768c`.
- Real-wallet contract YAML: parses and has no duplicate path keys.
- Frontend: lint PASS; 87 unit tests PASS; 90 frontend paths checked against 325 backend paths; typecheck PASS; production build PASS.
- Financial Service: 38 unit/contract tests PASS; local boundary script PASS for DDL denial, read-only denial, RLS isolation, network isolation, credential separation and secret-log scan.
- Governance: 8 unit tests PASS; exact-head runner FAILS CLOSED with `wrong head` for the currently pinned candidate.

## Supply chain

- Frontend npm audit: zero vulnerabilities.
- Backend and Financial Service images: zero fixed HIGH/CRITICAL findings.
- Frontend lockfile: zero HIGH/CRITICAL findings.
- Financial Service and governance gitleaks history scans: PASS.
- Backend/frontend current tracked source: no actionable secret after exclusions and RFC sample classification.
- Historical gitleaks candidates: 17 backend, one frontend; external validation/rotation required.
- Backend SBOM SHA256: `3fe15dfbfaa25be65b7423fb33f39d07d99cb012a3a9cf1f657129d5d2bab972`.
- Financial Service SBOM SHA256: `41c592fd06a9c0142cf4501eb5c1ad73a19ded089b61c6d5b66d09cc06776470`.

## Certification disposition

The checked-out code is executable and test-green after the focused fixes, but whole-platform canonical-authority certification is BLOCKED. Active mission implementations remain split across sibling PR stacks with unresolved semantic model, migration, state-machine, event and authority conflicts. Those protected integration decisions cannot be fabricated in this audit branch.
