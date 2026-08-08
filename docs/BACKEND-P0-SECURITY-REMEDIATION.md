# Backend P0 Security Remediation

## Scope

This branch derives from frozen candidate `34814195ab86b00ac2f5013bbf9946d732fb6c8e`. It changes application configuration and the runtime image only; it does not change production, the Financial Service, or any real-money feature state.

## Credential remediation

- Credential-shaped provider defaults were removed from source.
- NewsData, Polygon, and CoinGecko credentials are accepted through their environment variable or corresponding `_FILE` secret reference.
- Supplying both forms, an unreadable secret file, or an empty secret file fails configuration closed.
- Runtime provider calls fail closed before network access when their required credential is absent.
- Provider credentials are transmitted in request parameters or headers and are never embedded in logged URLs.
- Current-source secret scanning is required to report zero findings.

The twelve historical provider findings remain part of immutable Git history. Rewriting shared history is outside this remediation. The non-secret provider ownership and rotation actions are tracked in `SECURITY-CREDENTIAL-ROTATION-CHECKLIST.md`; independent evidence of revocation or rotation remains a release gate.

The sole scanner exception matches the exact RFC 6455 WebSocket health-check nonce. It is a protocol test fixture, not a credential, and the exception does not allowlist a file or a general secret pattern.

## Runtime image

The application image uses separate Alpine-based Python 3.11 builder and runtime stages. Compilers, development headers, Linux headers, and packaging tools remain in the discarded builder stage. The runtime stage contains the virtual environment, application code, and runtime libraries, runs as an unprivileged user, and upgrades Alpine packages during the build.

## Verification requirements

Before the branch is eligible for independent review, preserve evidence for:

- PostgreSQL 16 migration from zero, system check, and migration-drift check;
- complete and focused P0 test suites;
- rollback and reapply against disposable PostgreSQL;
- current-source secret scan and full-history scan;
- dependency and exact-image vulnerability scans;
- CycloneDX SBOM and immutable image digest;
- absence of build toolchain packages from the runtime stage.

Any source or dependency change after the candidate SHA is frozen invalidates this evidence and requires a new image, bundle, and complete certification run.

## Release boundary

No remaining vulnerability or historical credential exposure is silently suppressed. Risk acceptance is not self-approved. Merge remains unauthorized until independent security reviewers disposition remaining historical exposure and validate provider rotation evidence.
