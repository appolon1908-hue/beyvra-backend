# Webhook Inventory

| Webhook | Provider | Path | Authentication | Timestamp | Replay | Inbox | Tested | Classification |
|---|---|---|---|---|---|---|---|---|
| Compliance result | governed compliance adapter | `/api/v1/compliance/webhooks/{provider_key}` | HMAC-SHA256 over provider/timestamp/event/body | ±300 s plus result validity | provider event ID + payload hash | `ComplianceInboxEvent` | signature, stale/future, duplicate, conflict, malformed, unknown result | CANONICAL |
| Generic governed provider | configured adapter | `/api/v1/webhooks/{provider}/{purpose}` | HMAC-SHA256 over provider/purpose/timestamp/event/body | -300/+30 s | unique provider/purpose/event + hash | `WebhookInboxEvent` | old/current secret, 100 duplicates, malformed, oversized, unknown/dead-letter | CANONICAL |
| Stripe compatibility | Stripe | `/api/payment/stripe_webhook/` | Stripe native signature verifier | provider-native | legacy transaction state | none | fail-closed under immutable real-money flags | DEPRECATE / DISABLED |
| Notification staging sink | Beyvra fixture sender | `/api/notification/staging-receiver/` | staging-only configured secret and signed delivery | fixture contract | delivery uniqueness | `WebhookDelivery` | existing staging fixture suite | KEEP_COMPATIBILITY |
| Custody/payment/execution future handlers | none activated | none | n/a | n/a | n/a | n/a | `PROVIDER_NOT_AVAILABLE` / `FEATURE_DISABLED` | NOT_APPLICABLE |

`CUSTODY_PROVIDER_ACTIVATED=NO`, `PAYMENT_PROVIDER_ACTIVATED=NO`, and `EXECUTION_PROVIDER_ACTIVATED=NO`. No production or real-provider callback was invoked during certification.
