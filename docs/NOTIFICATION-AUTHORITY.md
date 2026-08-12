# Notification authority

Canonical notifications separate business events, versioned templates, and provider adapters. Channels are IN_APP, EMAIL, PUSH, and future SMS (no provider activation). Payload variables are allowlisted and may not contain credentials, tokens, raw support secrets, or full financial identifiers.

Security and financial categories are mandatory where policy requires. Deterministic `(tenant, account, channel, dedup_key)` uniqueness prevents storms. Business commits write to the outbox; consumers use `ProcessedEvent` for one effect.

Private realtime delivery is exposed only at `/ws/v2/`. The one-time websocket ticket establishes the user; client messages cannot select an account or tenant. Each connection joins only a SHA-256-derived tenant/account group, and the server emits an allowlisted notification representation without delivery diagnostics, staff context, or tenant/account identifiers. Anonymous connections close with code `4401`; the stream is read-only.
