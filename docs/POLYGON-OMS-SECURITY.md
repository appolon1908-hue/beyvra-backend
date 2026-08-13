# Polygon OMS security controls

- No OMS client, credentials, bearer token, or signing key in application/frontend.
- TLS required; production and non-allowlisted hosts forbidden by the future adapter.
- Connect, request, and overall deadlines required; no infinite waits.
- Retry only 408/429/confirmed transient 5xx, bounded to five attempts; honor numeric `Retry-After`.
- Never blindly retry a lost mutation response. Lookup by operation/idempotency reference first.
- Circuit states are `CLOSED`, `OPEN`, and `HALF_OPEN`; opening fails financial operations closed.
- Validate Decimal strings, status enums, schemas, asset/network pairs, and ownership.
- Reject SSRF by using fixed owner-reviewed base URLs, never caller-provided URLs.
- Do not log entity payloads, bearer tokens, signing keys, bank details, full wallet identifiers, or raw provider errors.
- Append-only audits record request/denial, webhook acceptance/state change, reconciliation mismatch, and governance changes using opaque references.

Provider governance progresses through `DISCOVERED`, `CONFIGURED`,
`CREDENTIAL_PRESENT`, `TECHNICALLY_CERTIFIED`, `SECURITY_APPROVED`,
`COMPLIANCE_APPROVED`, `FINANCIAL_APPROVED`, `STAGING_APPROVED`, and
`PRODUCTION_APPROVED`. `DISABLED` is the effective state until every independent
gate is satisfied. No actor may self-approve a protected transition.

Metrics use bounded category/result labels only:
`beyvra_oms_requests_total`, `beyvra_oms_failures_total`,
`beyvra_oms_duration_seconds`, `beyvra_oms_rate_limited_total`,
`beyvra_oms_webhooks_total`, `beyvra_oms_webhook_failures_total`,
`beyvra_oms_unknown_outcomes_total`, and
`beyvra_oms_reconciliation_violations_total`.
