# Compliance provider governance

States: `DISCOVERED`, `CONFIGURED`, `CREDENTIAL_PRESENT`, `TECHNICALLY_CERTIFIED`, `SECURITY_APPROVED`, `COMPLIANCE_APPROVED`, `STAGING_APPROVED`, `PRODUCTION_APPROVED`, `DISABLED`. Default is `DISABLED`. The public interface is `ComplianceProvider`; provider schemas never cross the API boundary. Session creation returns `PROVIDER_NOT_AVAILABLE` unless all required approvals exist. This change activates no provider and sends no PII externally.
