# Compliance operations

Cases use OPEN, IN_REVIEW, ESCALATED, RESOLVED_APPROVED, RESOLVED_REJECTED, CLOSED and append-only events. Viewer, analyst, and manager scopes are distinct. Sensitive overrides record before/after, rationale, maker, checker, timestamps, and expiry; self-approval is rejected. Monitor state counts, restriction counts, open/aging cases, provider failures/health, decisions, and event-processing failures with bounded labels only. Reconciliation must report zero allowed decisions against blocked state, zero restricted-account allowed trades, and zero missing audit events.

Retention: preserve profiles, decisions, cases, case events, overrides, and audits until legal/compliance retention is approved. Do not automatically delete. Store opaque provider references instead of duplicate documents.
