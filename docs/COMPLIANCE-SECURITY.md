# Compliance security and privacy

## Data boundary

PII includes identity, address, DOB, document images/references, and tax identifiers. Raw PII is prohibited in logs, metrics, traces, URLs, event subjects, alerts, source control, eligibility snapshots, and realtime messages. Public APIs expose only safe state names, restriction reason codes, actionable requirements, and timestamps. They exclude provider notes and schemas, raw match details, risk scores, case notes, evidence references, request IDs, document data, and tax values.

The canonical profile stores state and opaque evidence/provider references, not source documents. Case-event metadata is allow-listed to opaque assignment, note, reason, and resolution references. Retain compliance profiles, decisions, restrictions, cases, events, overrides, inbox records, and audit evidence until an approved legal retention schedule authorizes disposal; no automatic deletion is introduced.

## Access and integrity

Tenant scope is derived server-side from authenticated organization membership. `compliance_viewer`, `compliance_analyst`, and `compliance_manager` form an explicit least-privilege hierarchy; generic administrator status grants no compliance role. Clearing overrides and restriction removal use independent maker/checker approval, reject self-approval and stale state, and require opaque verified evidence when granting KYC, AML, or sanctions clearance.

Audit events, case events, and eligibility decisions are append-only in application code and protected by PostgreSQL update/delete rejection triggers. Provider callbacks authenticate the provider, bind event ID and body into the signature, enforce delivery and result freshness, and use inbox uniqueness with content-hash conflict detection.

## Encryption statement

No new field-level encryption mechanism was introduced and no encryption claim is made. Database, volume, backup, and legacy document-storage encryption remain environment controls outside this change and require independent infrastructure evidence before production approval. Provider webhook secrets remain environment-supplied and are never returned by an API.
