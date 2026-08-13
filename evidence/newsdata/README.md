# NewsData certification evidence — 2026-08-11

- NewsData-focused/provider/API suite: 52 passed on isolated PostgreSQL 16.
- Full backend discovery: 260 tests executed; 250 passed and 10 unrelated environment-dependent tests failed because the local runner lacked API-token pepper/Celery configuration and shared registration throttling state. No NewsData test failed.
- Migration: from zero PASS; drift NONE; rollback PASS; reapply PASS on isolated PostgreSQL 16.
- OpenAPI generation/validation: PASS.
- Frontend boundary: typecheck PASS, lint PASS, production build PASS, chart/news realtime unit suite 65 PASS.
- Current working-tree Gitleaks: zero findings. A local full-history scan found 13 pre-existing redacted findings; that self-referential report is intentionally not committed and this change does not claim historical remediation.
- `pip-audit`: zero known dependency vulnerabilities.
- Trivy source/config: zero high/critical vulnerabilities, secrets, or misconfigurations after making the Nginx image non-root. Raw scanner JSON is retained outside Git because scanner metadata can resemble credentials to independent scanners.
- Exact local backend image `sha256:28933357d6e846ff29037709f00bc37c4711fffafed531a4b8f44198f5edc86e`: zero high/critical vulnerabilities, secrets, or misconfigurations. Raw scanner JSON is retained outside Git.
- CycloneDX filesystem and image SBOMs are included.
- Live NewsData requests: zero; approval and entitlement gates are absent.
- Real financial effects and outbound execution: zero.
