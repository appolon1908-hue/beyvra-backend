# Polygon OMS webhook inventory

Official catalog reviewed 2026-08-11: [webhook events](https://docs.polygon.technology/api-reference/webhook-events) and [receiving webhooks](https://docs.polygon.technology/payments/guides/receiving-webhooks).

## Envelope and delivery contract

| Field | Contract |
| --- | --- |
| Event | `event`; the five `*.statusChanged` variants use `eventType`. |
| Delivery ID | `id` (`whd_`), stable across retries and the deduplication key. |
| Producer event ID | Optional `eventId` (`evt_`); not the per-endpoint dedup key. |
| Timestamp | `createdAt`, optional `occurredAt`; signature timestamp is header `t`. |
| Ordering | Optional per-resource monotonic `sequence`; delivery ordering is best effort. |
| Payload | Full changed resource under `data`; retain only allowlisted provenance/state. |
| Retry | At least once; 10 attempts over roughly three days, then failed. |
| Retention | Delivery history documented as 30 days by default. |

## Current documented event catalog

- Transaction: `transaction.statusChanged`.
- Cash-in: `cashIn.created`, `cashIn.completed`, `cashIn.expired`.
- Virtual-account lifecycle: `virtualAccount.provisioned`, `.active`, `.frozen`,
  `.closed`, `.deleted`, `.failed`, and `.statusChanged`.
- Virtual-account deposits: `virtualAccount.deposit.pending`, `.settled`,
  `.failed`, `.returned`.
- Virtual-account crypto and fiat legs: each of
  `virtualAccount.cryptoTransfer` and `virtualAccount.fiatTransfer` with
  `.initiated`, `.pending`, `.settled`, `.failed`.
- Deposit-address lifecycle: `depositAddress.active`, `.frozen`, `.closed`,
  `.failed`, `.statusChanged`.
- Deposit-address crypto deposits: `deposit_address.crypto_deposit.pending`,
  `.settled`, `.failed`, `.needs_attribution`.
- Deposit-address payouts: each of `deposit_address.ach_payout`,
  `.wire_payout`, and `.intl_wire_payout` with `.initiated`, `.pending`,
  `.settled`, `.failed`, `.returned`; `deposit_address.crypto_payout` has the
  same states except `.returned`.
- External accounts: `externalAccount.created`, `.verified`, `.declined`,
  `.deleted`, `.statusChanged`.
- Counterparty: `counterparty.statusChanged`.
- Endorsement: `endorsement.updated`, `endorsement.active`.
- Wallet: `wallet.provisioned`.
- Explicit compliance subscriptions: `transaction.fiatToCrypto.underReview`,
  `transaction.cryptoToFiat.underReview`, and
  `transaction.cryptoToCrypto.underReview`.
- Connectivity fixture: `webhook.test`.

Exact subscriptions must be captured from the entitled account; wildcard
subscriptions exclude compliance-review events.

## Verification

`Webhook-Signature: t=<unix>,v1=<hex>` uses HMAC-SHA256 over
`<t>.<raw request body>`. Compare in constant time and reject timestamps older
than 300 seconds. Persist the verified delivery ID uniquely before acknowledging.
Apply only newer resource sequences. Unknown event/state, sequence gap, or
invalid transition causes no mutation and enters a safe operator-visible
dead-letter/reconciliation path.

The intended owner route is Financial Service `POST /internal/v1/webhooks/polygon-oms`.
The suggested public-looking `/api/v1/webhooks/polygon-oms` is intentionally not
registered in the application backend because that would violate the trust boundary.
