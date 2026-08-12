# Surveillance Evidence

Evidence rows contain bounded features, opaque order references, canonical instrument identity, rule and policy versions, time windows and SHA-256 evidence hashes. Surveillance audit is append-only in application code and PostgreSQL triggers. Generic logs and metrics contain no account, user, instrument, case, or event identifiers.

Future evidence export is an authorized operator workflow only. It must include a manifest and omit unnecessary PII. No external regulatory submission is implemented.
