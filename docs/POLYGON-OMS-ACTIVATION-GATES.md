# Polygon OMS activation gates

Current effective state: `DISABLED`.

The outbound guard requires, in precedence order:

1. `ALL_FINANCIAL_MUTATIONS_HALTED=false` through independent governance.
2. `POLYGON_OMS_HALTED=false` through a governed kill-switch release.
3. `POLYGON_OMS_ENABLED=true`.
4. approved non-production environment and fixed base URL.
5. credential reference present in Financial Service secret storage.
6. operation approval and feature-specific flag.
7. canonical compliance approval with no restriction/freeze.
8. independent financial-owner approval.

Any missing gate returns deny-before-network. Production additionally requires
`POLYGON_OMS_PRODUCTION_ENABLED=true`, production access, security, compliance,
financial, change-management, and repository-owner approval. This mission grants
none of those.

Sandbox certification requires confirmed OMS account entitlement and authorized
credential ownership. Until then: `LIVE_OMS_READ_TEST=BLOCKED_EXTERNAL`,
`SANDBOX_CERTIFICATION=BLOCKED_EXTERNAL_ACCESS`.

Custody selection, jurisdictions, rails, supported assets/networks, retention,
and provider-vs-ledger contractual authority require external financial/legal
decisions. Cross-chain requires a separate approved feature and remains false.
