# Notification authority

Canonical notifications separate business events, versioned templates, and provider adapters. Channels are IN_APP, EMAIL, PUSH, and future SMS (no provider activation). Payload variables are allowlisted and may not contain credentials, tokens, raw support secrets, or full financial identifiers.

Security and financial categories are mandatory where policy requires. Deterministic `(tenant, account, channel, dedup_key)` uniqueness prevents storms. Business commits write to the outbox; consumers use `ProcessedEvent` for one effect.
