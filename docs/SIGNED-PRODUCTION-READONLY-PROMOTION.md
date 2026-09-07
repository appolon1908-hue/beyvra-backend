# Signed production-readonly promotion contract

This repository permits production read-only promotion only through `.github/workflows/promote-production-readonly.yml`.

The workflow requires a successful `Certify deployed immutable Beyvra backend` staging run and downloads its checksum-protected `production-promotion-manifest.json`. It rejects promotion unless that manifest records:

- `target: staging-readonly`;
- `certification_result: PASS`;
- `rollback_rehearsal: PASS`;
- `zero_live_effects: PASS`;
- exact protected-main source SHA;
- exact backend and edge `repository@sha256` digests;
- all live-money and external-effect authorizations as false.

Both image subjects must also have valid GitHub/Sigstore certification attestations signed by `.github/workflows/certify-deployment.yml`. Their OCI revision labels must equal the certified source SHA.

The protected `production-readonly` environment must set `CANARY_TRAFFIC_PERCENT` to `0` or `1` and `EXTERNAL_CANARY_ROUTING_VERIFIED` to `true`. The promotion dispatcher calls the existing deploy workflow with `publish_images=false`, so production cannot rebuild or retag the candidate.

This contract never authorizes live trading, real money, deposits, withdrawals, payments, transactional email, external execution, schema migrations, simulation execution, or legacy realtime fallback.
