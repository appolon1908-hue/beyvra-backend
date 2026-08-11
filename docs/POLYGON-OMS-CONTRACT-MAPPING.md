# Polygon OMS contract mapping

## Canonical mappings

| Beyvra concept | OMS resource | Rule |
| --- | --- | --- |
| Account reference | Customer (`cst_`) | Store an opaque mapping; never replace Beyvra identity. |
| Financial wallet | Custodial wallet (`wlt_`) if approved | Preserve asset, chain/network, custody model, status. |
| Quote | `POST /quotes` result | Decimal strings only; quote has no financial effect. |
| Operation | Transaction (`txn_`) | Execute an open quote with stable idempotency key. |
| On-ramp | fiat source to crypto destination | Documented, entitlement unknown, disabled. |
| Off-ramp | crypto source to fiat destination | Documented, entitlement unknown, disabled. |
| Transfer | inferred source/destination route | Documented, entitlement unknown, disabled. |
| Compliance | customer endorsements/review | Input to Beyvra policy, never automatic authority. |

Canonical transaction mapping: `processing -> PROCESSING`, `awaitingAction ->
REQUIRES_ACTION`, `completed -> SETTLED`, `failed -> FAILED`. Any undocumented
value becomes `UNKNOWN`; it never becomes settled.

Canonical KYC mapping includes `NOT_STARTED`, `PENDING`, `IN_REVIEW`,
`APPROVED`, `REJECTED`, `EXPIRED`, and `REQUIRES_UPDATE`. Any unknown provider
value maps to `IN_REVIEW`, not approval.

Money is represented as `Decimal` plus lowercase asset and explicit network.
Runtime support must come from `GET /networks`; documentation examples are not
an entitlement inventory. A canonical `AssetNetwork` also records network ID,
decimals, and contract address when applicable.

Provider errors map internally to `VALIDATION_ERROR`, `COMPLIANCE_REQUIRED`,
`OPERATION_NOT_ALLOWED`, `INSUFFICIENT_FUNDS`, `IDEMPOTENCY_CONFLICT`,
`PROVIDER_UNAVAILABLE`, or `UNKNOWN_OUTCOME`. BeyvraErrorMapper remains the only
customer error authority.
