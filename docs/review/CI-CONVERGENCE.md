# CI convergence

Backend CI uses PostgreSQL 16, migration drift checks, focused security/realtime tests, gitleaks, image build and Trivy. The first-pass audit found these convergence gaps:

- CI certifies the current branch, while active architecture missions are split across sibling PR stacks.
- Focused tests do not constitute the required full backend suite or migration-from-zero/reapply proof.
- No cross-repository backend/frontend/Financial Service contract matrix pins compatible SHAs.
- OpenAPI and realtime inventories are not generated and diffed as build artifacts.
- SBOM generation is not a required checked-in gate.
- Deploy workflow is separate from the audit and was not invoked.

Protected integration must test the exact combined SHA set before any merge or deployment.
