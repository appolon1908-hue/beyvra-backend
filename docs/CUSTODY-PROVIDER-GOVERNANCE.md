# Custody and payment provider governance

States: `DISCOVERED`, `CONFIGURED`, `CREDENTIAL_PRESENT`, `TECHNICALLY_CERTIFIED`, `SECURITY_APPROVED`, `COMPLIANCE_APPROVED`, `FINANCIAL_APPROVED`, `STAGING_APPROVED`, `PRODUCTION_APPROVED`, `DISABLED`. Default is `DISABLED`; no approval is inferred.

The central outbound guard requires provider enabled, approved environment and operation, compliance approval, financial approval, feature enabled, the matching global provider activation switch, and `REAL_MONEY_ENABLED`. Any false value denies before constructing a network request. Caller-supplied approvals cannot override the global switches. Credentials may exist only in an approved secret store, protected environment or mounted secret and never frontend, Git, logs, metrics, traces, API errors or audit payloads. Egress allowlists must name only separately approved hosts; none are approved by this mission.

## Future webhook boundary

Provider webhook processing is inert until a separately approved integration supplies a protected per-provider secret. Verification requires an exact allowlisted provider identity, bounded provider event ID, HMAC-SHA256 signature over timestamp/event/provider/raw body, constant-time comparison, and a five-minute past/future replay window. The payload must be a versioned `financial.*.v1` envelope and is rejected if it contains secret-bearing keys.

Only a canonical payload hash and UUID-derived receipt enter the transactional inbox. Raw provider bodies and signatures are not persisted. The inbox atomically commits the handler and receipt: identical delivery is a no-op, changed tenant/type/payload under the same event identity is a replay conflict, and handler failure rolls back the receipt for safe retry. The isolated test fixture proves 100 concurrent duplicate deliveries yield exactly one business effect. Verification performs no outbound request and does not imply provider approval.
