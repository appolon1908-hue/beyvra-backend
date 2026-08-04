# Codestra Demo domain contract

## Product boundary

This contract describes the staging Demo platform only. Wallets contain virtual
funds, orders are simulated, and no payment, deposit, withdrawal, custody or
external order-routing operation is permitted.

## Canonical aggregates

- `Organization` is the tenant boundary.
- `User` belongs to an organization through `OrganizationMembership`.
- `Wallet` is owned by `(organization, user)` and is never read without both
  predicates.
- `Trade` belongs to `(organization, wallet, user)` and uses server quotes and
  server timestamps.
- `DemoLedgerEntry` is append-only and records every credit, reservation,
  release, settlement and refill.
- `WebhookSubscription` and `WebhookDelivery` are tenant-scoped.

## Order state machine

```text
DRAFT -> OPEN -> SETTLING -> WON | LOST | DRAW
             \-> REJECTED | CANCELLED | QUOTE_UNAVAILABLE | MARKET_STALE
```

The server owns opening/closing prices, timestamps, expiry, result, payout and
balance changes. Every mutation requires an idempotency key. Replays return the
original result and cannot create a second trade or ledger entry.

## Wallet invariants

1. `available >= 0` and `reserved >= 0`.
2. `available + reserved` equals the ledger-derived wallet balance.
3. A reservation is created once per accepted order.
4. Settlement releases/resolves a reservation exactly once.
5. Refill resets available Demo funds to the configured target; it does not
   repeatedly add the target amount and never deletes history.
6. All balance mutations execute inside a database transaction with row
   locking.

## Tenant isolation

Every wallet, trade, preference, notification, media and webhook query must
derive organization identity from the authenticated session or an authorized
membership. Client-provided tenant IDs are hints only and are rejected unless
membership authorization succeeds.

## Webhook delivery

Delivery payloads are signed with HMAC-SHA256 over the exact JSON bytes and carry
event ID and signature-version headers. Delivery attempts are bounded, inactive
subscriptions dead-letter immediately, and `(subscription, event)` is unique.
