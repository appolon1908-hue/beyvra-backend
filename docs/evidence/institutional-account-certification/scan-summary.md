# Security scan summary

Scans were performed against the current source tree and candidate container.
Raw reports containing scanner-matched substrings are intentionally not
committed.

| Scan | Result |
|---|---|
| Gitleaks current source (`--no-git`, redacted) | PASS — 0 findings |
| Trivy dependency critical, ignore unfixed | PASS — 0 |
| Trivy container critical, ignore unfixed | PASS — 0 |
| Trivy configuration high/critical | PASS — 0 |
| CycloneDX SBOM generation | PASS |
