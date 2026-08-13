# Financial Service owner-review proposal: Polygon OMS

Financial Service reviewed SHA: `c75da4b069df87344a35da2ad772af526f844770`.
This proposal does not modify that repository.

## Proposed internal abstraction

`OpenMoneyStackProvider` should expose only documented, entitled capabilities:
`health`, `capabilities`, customer create/get/update, wallet create/get/list,
balance read, quote create/get, transaction execute/get/list, and eligible
cash-in/route operations. OMS documents a unified quote/transaction model rather
than separate generic on-ramp/off-ramp/transfer endpoints, so provider methods
should translate canonical intents into quote sources/destinations instead of
inventing endpoints. Cancellation must not exist unless account documentation
confirms support.

## Proposed Financial Service APIs

- deposit intent, withdrawal intent, transfer intent
- quote creation/read with no ledger effect
- operation lookup by Beyvra operation and idempotency reference
- reserve/release/settle orchestration using existing ledger authority
- provider reconciliation and safe status projection
- internal OMS webhook ingestion owned by Financial Service

Every mutation requires tenant/account context, stable idempotency key, policy
decision, compliance decision, financial approval evidence, and transactional
outbox. Webhooks require a unique inbox row, monotonic resource sequence, domain
mutation, outbox, and audit in one database transaction.

## Owner decisions required

- custody model and key-control contract
- enabled products, jurisdictions, corridors, rails, assets, and networks
- provider balance versus ledger legal/operational authority
- PII fields, processor terms, retention, and webhook history policy
- secret/certificate lifecycle and egress allowlist
- sandbox and production approval chains

Suggested OpenAPI changes belong in a separate owner-reviewed Financial Service
PR after these decisions. No Polygon-specific public Beyvra schema is proposed.
