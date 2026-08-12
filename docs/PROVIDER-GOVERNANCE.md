# Provider governance

Providers follow: `DISCOVERED → CONFIGURED → CREDENTIAL_PRESENT → TECHNICALLY_CERTIFIED → LICENSE_VERIFIED → SECURITY_APPROVED → COMPLIANCE_APPROVED → STAGING_APPROVED → PRODUCTION_APPROVED`. `DISABLED` is the default and may be entered from any state.

The persistent `ProviderDefinition` policy stores provider ID/type, enabled state, environment, license/security/compliance/staging/production approvals, asset/data allowlists, staleness limit, priority, failover permission, updater, and timestamp. The existing versioned `ProviderApproval` retains product/symbol/region scope and immutable approval evidence. Production approval has a database constraint requiring all preceding controls; runtime resolution additionally requires enabled, staging environment, license, security, compliance, and staging approval plus valid immutable approval/license/credential evidence. A credential alone cannot advance state.

Default records and missing records fail closed. Production emission additionally requires a production-specific resolver before any future activation; the current resolver is staging-only. `EXECUTION_PROVIDER_ACTIVATED=NO` and market-data approval cannot authorize execution.

