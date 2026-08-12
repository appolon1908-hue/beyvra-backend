# Beyvra domain reference inventory

Snapshot: 2026-08-12 UTC. Source heads: backend `ed32b3b7210db209bdeb426bb172f84a4cbd3843`, frontend `f27023d0013ef6b625f1d64501f23f1d8cf2cae5`.

This inventory separates public identity from compatibility identifiers. It does not authorize DNS, TLS, edge, staging, OAuth-provider, Financial Service, or production changes.

| Path / family | Value | Classification | Action |
|---|---|---|---|
| Backend active settings, `.env.example`, Nginx template, Compose, Centrifugo, email/link helpers | `beyvra.com`, `api.beyvra.com`, `staging.beyvra.com`, `/ws/v2/` | `SAFE_TO_REPLACE` (already converged) | Keep; enforced by `scripts/check_public_identity.py`. |
| `contracts/openapi/codestra-real-wallet-v1.yaml` | `https://api.beyvra.com/api/v1` | `SAFE_TO_REPLACE` (already converged) | Keep public server; retain filename for contract-path compatibility. |
| `FX/apps/trading/tests/test_p0_foundation.py` | assertion rejecting `codestra.cloud` | `TEST_FIXTURE` | Keep as a negative regression assertion. |
| `docs/BEYVRA-PUBLIC-IDENTITY-INVENTORY.md` | historical mention of `staging.codestra.cloud` | `HISTORICAL_EVIDENCE` | Keep; it records the completed source migration and cutover prerequisites. |
| Frontend active source, runtime template, `.env.example`, metadata, sitemap and robots | Beyvra public URLs | `SAFE_TO_REPLACE` (already converged) | Keep; frontend brand check guards active surfaces. |
| Frontend `docs/platform-parity/staging-handoff.md` | old staging URL | `PUBLIC_DOMAIN_STALE` | Replace with `https://staging.beyvra.com/`. |
| Frontend redesign audit | old staging capture URL | `HISTORICAL_EVIDENCE` | Retain and label as a historical pre-convergence capture. |
| Frontend name-migration inventory | old staging compatibility statement | `HISTORICAL_EVIDENCE` | Retain as a dated record; current live edge removal remains separately gated. |
| `/srv/codestra/Caddyfile` | `staging.codestra.cloud` compatibility host | `PUBLIC_DOMAIN_STALE` / live edge | Do not mutate in this source-only tranche. Removal requires explicit production-change authorization, traffic review and rollback. |
| `/srv/codestra/Caddyfile` | other Codestra products and hosts | `LEGAL_ORGANIZATION_REFERENCE` / unrelated product | Out of scope; do not alter. |
| Internal metrics, headers, cookie/storage keys, NATS names, secret-mount paths, Docker identities | `codestra*` | `INTERNAL_CODE_NAMESPACE` | Retain until a versioned compatibility migration exists. |
| Migrations, database identifiers, Git remotes and immutable certification evidence | `codestra*` | `GIT_REPOSITORY_IDENTITY` / `HISTORICAL_EVIDENCE` | Retain to preserve identity and audit integrity. |

## Measured source state

- Backend lines containing `codestra`: 183.
- Frontend lines containing `codestra`: 168.
- Active backend public-domain references: 0 (excluding the negative test and historical inventory).
- Active frontend public-domain references: 0 after the staging-handoff correction.
- Browser-facing hardcoded `49.12.145.107` references: 0.
- Active OpenAPI Codestra public servers: 0.

## External state

All six requested DNS names resolve to `49.12.145.107`; `www.beyvra.com` is a CNAME to the apex. `staging.beyvra.com` has a valid Let's Encrypt certificate. The apex, `www`, `api`, `admin`, and `platform` do not currently complete a valid TLS handshake at the public edge and require certificate/edge-owner action.
