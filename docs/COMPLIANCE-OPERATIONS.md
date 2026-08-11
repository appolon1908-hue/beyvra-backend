# Compliance operations

Cases use OPEN, IN_REVIEW, ESCALATED, RESOLVED_APPROVED, RESOLVED_REJECTED, CLOSED and append-only events. Viewer, analyst, and manager scopes are distinct. Sensitive overrides record before/after, rationale, maker, checker, timestamps, and expiry; self-approval is rejected. Monitor state counts, restriction counts, open/aging cases, provider failures/health, decisions, and event-processing failures with bounded labels only. Reconciliation must report zero allowed decisions against blocked state, zero restricted-account allowed trades, and zero missing audit events.

Scoped operations are exposed under `/api/v1/admin/compliance/`. A compliance viewer can read tenant-scoped cases, an analyst can create cases/events/restrictions and request overrides, and only a compliance manager can provide the independent checker approval. A generic administrator receives no compliance authority. Audit and case-event database triggers reject updates and deletes. State mutations and their safe private realtime notifications commit through the shared transactional outbox.

Retention: preserve profiles, decisions, cases, case events, overrides, and audits until legal/compliance retention is approved. Do not automatically delete. Store opaque provider references instead of duplicate documents.
