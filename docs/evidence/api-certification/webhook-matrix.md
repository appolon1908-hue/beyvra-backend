# Webhook contract matrix

The provider-neutral handler at `/api/v1/webhooks/{provider}/{purpose}` was certified with sanitized fixture payloads.

| Case | Expected | Result |
|---|---|---|
| Valid HMAC, timestamp and provider identity | accepted once | PASS |
| Bad or missing signature | reject before business logic | PASS |
| Expired/future timestamp | reject | PASS |
| 100 duplicate deliveries | one inbox/business effect | PASS |
| Same event ID, different body | replay conflict | PASS |
| Invalid JSON/encoding/oversized body | safe rejection | PASS |
| Unknown event | dead-letter with operator visibility | PASS |
| Provider not governed/configured | provider unavailable, no mutation | PASS |

Staging retains no external provider secret. Signature certification used only a test secret and synthetic fixtures; no external provider was activated.
