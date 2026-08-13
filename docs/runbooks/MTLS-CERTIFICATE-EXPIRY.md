# mTLS certificate expiry and rotation

Test/staging only: verify issuer, SAN/service identity, scope and old expiry; deploy the new certificate with a bounded overlap; verify both during overlap; remove old material; confirm identity/scope; retain rollback until reconciliation passes. Expired, wrong-CA and wrong-identity certificates must fail. Never disable verification. Production rotation requires separate authorization.
