# Beyvra one-click read-only go-live

The authoritative manual entrypoint is:

```text
Actions → Beyvra — One-Click Read-Only Go Live → Run workflow
```

After this file and `.github/workflows/go-live-readonly.yml` reach protected `main`, the workflow page is:

```text
https://github.com/appolon1908-hue/beyvra-backend/actions/workflows/go-live-readonly.yml
```

The workflow has no release inputs. It resolves the current protected-main SHA in both `beyvra-backend` and `beyvra-frontend`, verifies their required checks, and generates auditable change IDs from its own immutable workflow run ID.

## Complete sequence

A single manual dispatch performs this sequence and stops at the first failed gate:

1. build the backend and edge images once from digest-pinned bases;
2. generate SBOM and BuildKit provenance;
3. sign and verify both exact OCI digests before deployment;
4. deploy the exact backend tuple to `staging-readonly`;
5. certify source/digest readback, readiness, API behavior, security headers, private metrics, zero live effects, backups, and controlled rollback;
6. promote those same backend digests to a protected production read-only canary and certify them again;
7. bind the frontend build to the exact signed backend staging certification;
8. build, sign, verify, and deploy the exact frontend digest to `staging-readonly`;
9. certify frontend/backend identity, same-origin behavior, read-only capabilities, security headers, mutation rejection, controlled rollback, candidate restoration, and static integrity;
10. require the matching signed backend production certification;
11. promote the same frontend digest to the protected production read-only canary and certify the complete tuple.

## Required repository secret

`beyvra-backend` must contain a repository Actions secret named:

```text
BEYVRA_RELEASE_BOT_TOKEN
```

Use a fine-grained release identity with access only to `appolon1908-hue/beyvra-backend` and `appolon1908-hue/beyvra-frontend`. It needs repository contents read, Actions read/write, packages read, and attestations read. It does not need SSH, server secrets, branch-protection administration, or permission to bypass protected environments.

The child deployment and certification workflows continue to use their own protected environment secrets and short-lived GitHub OIDC identities. The cross-repository token only dispatches workflows, reads their state, and downloads non-secret certification artifacts.

## Fail-closed rules

The button does not bypass pull-request approval, required checks, protected environments, signed artifact verification, staging certification, rollback, or production canary controls.

The chain stops when any of these conditions occurs:

- either protected-main SHA changes during the run;
- a required main check is missing or not successful;
- an automatic release intent is enabled;
- a workflow run cannot be correlated uniquely;
- a build, deployment, certification, or promotion workflow fails;
- a source SHA or image digest differs;
- a required signature, certification predicate, checksum, backup, rollback result, or zero-effect proof is missing;
- the previous immutable candidate is unavailable;
- the frontend is not bound to the exact signed backend certification;
- `CANARY_TRAFFIC_PERCENT` is not `0` or `1`;
- independent canary routing verification is absent;
- any live-effect authorization is true.

## Production boundary

This is a production **read-only** release only. It does not authorize live trading, real money, deposits, withdrawals, payments, transactional email, broker execution, schema migrations, simulation execution workers, or legacy realtime fallback.

Merging the release PR does not deploy by itself. `.release/intent.json` remains disabled; deployment starts only from the manual workflow button.
