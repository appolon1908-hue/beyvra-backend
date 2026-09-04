# Beyvra immutable read-only certification

The repository uses three separately reviewable stages:

1. `CI` validates the exact protected source.
2. `Publish and deploy immutable Beyvra backend` builds once for staging or
   reuses the exact staging digests for production.
3. `Certify deployed immutable Beyvra backend` binds itself to the deployment
   manifest and certifies the running candidate.

## Protected environment values

Both `staging-readonly` and `production-readonly` require the deployment
secrets and variables documented in `docs/PRODUCTION-READONLY-PROMOTION.md`,
plus:

- `VERIFICATION_BASE_URL`: an HTTPS origin that deterministically reaches the
  candidate rather than a weighted public route;
- `CERTIFICATION_TOKEN_FILE`: a server-local, mode `0600` or stricter file
  containing a pre-provisioned read-only synthetic access token;
- `CANARY_TRAFFIC_PERCENT`: `0` through `100` in staging and no more than `1`
  in production;
- `EXTERNAL_CANARY_ROUTING_VERIFIED`: `true` only after the independent ingress
  authority proves the declared production weight.

The token is never copied to GitHub, written to artifacts, or printed. It is
read only for non-destructive authenticated GET checks. Every mutation probe is
rejected by the read-only edge before it can reach Django.

## Certification evidence

A successful staging certification proves:

- exact source SHA plus backend and edge image digests;
- liveness, readiness, database-enforced read-only state, capabilities, and
  release identity;
- authenticated API contract coverage and anonymous authentication denial;
- security headers and public metrics denial;
- private application and StatsD exporter metrics availability;
- every live-effect counter remains exactly zero before and after probes;
- all live trading, real-money, deposit, withdrawal, transfer, payment,
  transactional-email, broker-routing, and legacy-realtime flags are disabled;
- local and off-host PostgreSQL backup checksums and archive readability;
- zero pending schema migrations;
- rollback to the complete previous immutable tuple and restoration of the
  candidate;
- measured rollback and candidate-restoration RTO;
- RPO zero and unchanged privacy-safe cryptographic database fingerprint.

Production certification rejects image rebuilding, canary traffic above one
percent, or an unverified external canary route. Production uses the same
staging-certified backend and edge digests and does not repeat the staging
rollback rehearsal.

## Stop conditions

The certification fails closed on source or digest mismatch, missing evidence,
readiness failure, database write capability, missing monitoring, API contract
failure, security-header regression, nonzero or moving live-effect counters,
backup failure, migration drift, incomplete previous-image identity, rollback
failure, data-fingerprint change, or canary-policy violation.
