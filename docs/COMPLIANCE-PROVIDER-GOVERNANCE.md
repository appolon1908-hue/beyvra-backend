# Compliance provider governance

The persisted states are `DISCOVERED`, `CONFIGURED`, `CREDENTIAL_PRESENT`, `TECHNICALLY_CERTIFIED`, `SECURITY_APPROVED`, `COMPLIANCE_APPROVED`, `STAGING_APPROVED`, `PRODUCTION_APPROVED`, and `DISABLED`. New rows default to `DISABLED`. State labels are evidence, not credentials and not an activation switch.

The public boundary is the provider-neutral `ComplianceProvider` interface: `create_session`, `get_session`, `get_verification`, `screen_identity`, `health`, and `capabilities`. Provider-native payloads must be normalized before entering domain services and never cross public APIs or realtime events.

Session creation currently always returns `PROVIDER_NOT_AVAILABLE`: there is no approved concrete provider adapter in this release. Merely inserting a governance row cannot activate external calls. A future adapter requires license, security, privacy, compliance, environment, credential, and staging approval evidence before bounded staging use; production additionally requires `PRODUCTION_APPROVED` and an explicit release change.

Callbacks require an approved provider key, an event ID, a fresh timestamp, and HMAC-SHA256 over `provider_key.timestamp.event_id.raw_body`. Inbox uniqueness produces one business effect for identical replay and rejects reuse of an event ID with different content. Result `occurred_at` is independently checked against the configured validity window, so a freshly delivered stale result is rejected.
