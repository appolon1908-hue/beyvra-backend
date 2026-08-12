# Security scan summary

Certification date: 2026-08-11.

- Gitleaks current backend source: 0 findings
- Gitleaks full backend history: 16 pre-existing findings retained behind the protected PR20 disposition/independent-review gate
- Gitleaks current frontend source: 0 findings
- Trivy filesystem vulnerabilities (HIGH/CRITICAL): 0
- Trivy configuration findings (HIGH/CRITICAL): 0
- Candidate backend container critical vulnerabilities: 0
- Frontend npm audit: 0 vulnerabilities
- Exact-candidate CycloneDX SBOM: `sbom.cdx.json`

The Nginx helper image was hardened to run as its non-root `nginx` user. No production or provider credentials are included in evidence.
