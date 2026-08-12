# Security results

```text
SECRET_SCAN=PASS (gitleaks candidate working tree, 0 findings)
DEPENDENCY_SCAN=PASS (npm audit, 0 vulnerabilities; Trivy image dependency scan, 0 HIGH/CRITICAL)
CONTAINER_SCAN=PASS (Trivy backend-app:local, 0 HIGH/CRITICAL)
SBOM=PASS (CycloneDX artifact checked in as backend-sbom.cdx.json)
REAL_TRADING_ENABLED=false
EXTERNAL_EXECUTION_ENABLED=false
REAL_SETTLEMENT_ENABLED=false
REAL_MONEY_ENABLED=false
OUTBOUND_LIVE_EXECUTION_REQUESTS=0
OUTBOUND_LIVE_SETTLEMENT_REQUESTS=0
REAL_FINANCIAL_EFFECTS=0
PRODUCTION_CHANGED=NO
```
