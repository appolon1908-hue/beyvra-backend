# Custody and payment provider governance

States: `DISCOVERED`, `CONFIGURED`, `CREDENTIAL_PRESENT`, `TECHNICALLY_CERTIFIED`, `SECURITY_APPROVED`, `COMPLIANCE_APPROVED`, `FINANCIAL_APPROVED`, `STAGING_APPROVED`, `PRODUCTION_APPROVED`, `DISABLED`. Default is `DISABLED`; no approval is inferred.

The central outbound guard requires provider enabled, approved environment and operation, compliance approval, financial approval, and feature enabled. Any false value denies before constructing a network request. Credentials may exist only in an approved secret store, protected environment or mounted secret and never frontend, Git, logs, metrics, traces, API errors or audit payloads. Egress allowlists must name only separately approved hosts; none are approved by this mission.
