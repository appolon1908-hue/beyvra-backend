# Provider Credential Rotation Checklist

Candidate baseline: `34814195ab86b00ac2f5013bbf9946d732fb6c8e`.

Historical scanner evidence identified credential-shaped values associated with NewsData, CoinGecko demo access, and Polygon. This checklist intentionally contains no credential values. Historical credentials must never be tested against providers.

For each provider:

- [ ] Assign the provider account owner and security owner.
- [ ] Identify the account using provider-side inventory and audit records, not the historical value.
- [ ] Revoke or rotate every possibly exposed credential.
- [ ] Record the provider-side revocation timestamp and non-secret credential identifier.
- [ ] Store the replacement in the approved secret manager or mounted secret file.
- [ ] Configure exactly one of the environment or `_FILE` references.
- [ ] Verify missing credentials fail closed before any provider request.
- [ ] Verify application logs and reports contain no credential value.
- [ ] Re-run current-source and complete-history secret scans.
- [ ] Obtain independent security confirmation before closing the historical exposure.

Provider ownership:

| Provider | Account owner | Security owner | Rotation evidence | Status |
|---|---|---|---|---|
| NewsData | Unassigned | Platform Security | Required | Open/blocking |
| CoinGecko demo API | Unassigned | Platform Security | Required | Open/blocking |
| Polygon | Unassigned | Platform Security | Required | Open/blocking |

The WebSocket health-probe value is an RFC 6455-style test nonce, not authentication material. The scanner exception is exact-value and exact-purpose constrained in `.gitleaks.toml`; it does not allowlist the file or any provider credential pattern.
