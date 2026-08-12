# Fraud and account-protection inventory

| Capability | Existing state | Classification | Canonical path |
|---|---|---|---|
| Login activity | `security.UserActivity`, login middleware | LEGACY / UNSAFE (raw IP and user agent) | `operations.SecurityEvent` with opaque network/device refs |
| Devices | `users.UserDeviceInfo` | LEGACY / DUPLICATE | `operations.DeviceIdentity` stores only a fingerprint hash |
| Sessions | JWT plus Django sessions | AUTHORITATIVE for newly issued tokens; transitional legacy tokens remain customer-compatible | `operations.AccountSession` plus `SessionBoundJWTAuthentication` |
| MFA/password reset | User flags and security settings | DUPLICATE | security events and session invalidation policy |
| Risk score/decision | anomaly helper | UI/heuristic only | `evaluate_account_risk()` |
| Freeze | user ban endpoints | UNSAFE / overly broad | `operations.AccountFreeze` |
| Fraud cases | security incident | LEGACY | `operations.FraudCase` |

Raw network data is not treated as certain geography. Existing `EncryptionKeys.key_value` storage is unsafe and is not part of the new authority; migration/removal requires a separately scoped secret-rotation review.
