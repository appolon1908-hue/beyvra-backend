# Remaining Codestra identifiers

Snapshot: 2026-08-12 UTC.

| Component family | Status | Justification |
|---|---|---|
| `codestra_*` and `codestra.*` metrics, alerts and dashboard queries | `INTENTIONAL_INTERNAL_IDENTIFIER` | Renaming would break time-series continuity and alert consumers; use dual emission before retirement. |
| `X-Codestra-*` signed/proxy headers | `INTENTIONAL_INTERNAL_IDENTIFIER` | Versioned protocol compatibility; requires a dual-header rollout. |
| Browser cookie/local-storage compatibility keys | `INTENTIONAL_INTERNAL_IDENTIFIER` | Preserves sessions and saved user state; existing Beyvra keys use legacy fallback where applicable. |
| NATS, JetStream, Centrifugo and durable identifiers | `INTENTIONAL_INTERNAL_IDENTIFIER` | Delivery, replay and deduplication identity must remain stable. |
| `/etc/codestra`, `/run/secrets/codestra`, Compose projects, networks, images and service units | `INTENTIONAL_INTERNAL_IDENTIFIER` | Operational identity only; changing it risks secret mounts and rollback. |
| OpenAPI artifact filenames and generated-client symbols | `INTENTIONAL_INTERNAL_IDENTIFIER` | Stable tooling/import paths; public titles, servers and error copy are Beyvra. |
| Django migration/database identifiers | `MIGRATION_STABILITY_REFERENCE` | Immutable schema history and database compatibility. |
| Repository remotes and repository names | `GIT_REPOSITORY_REFERENCE` | Repository identity is not a customer-facing domain. |
| Dated audits, backups and certification records | `HISTORICAL_EVIDENCE` | Preserve factual evidence and hashes. |
| Existing legal/company references where present | `LEGAL_ENTITY_REFERENCE` | Public brand migration does not authorize a legal-entity rename. |

Every remaining family is classified. A literal zero-name migration must be a separate, backward-compatible namespace project.
