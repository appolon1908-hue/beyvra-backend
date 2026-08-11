# Reservation and release contract

`reserve_funds` request: `account_ref`, `asset`, decimal-string `amount`, `purpose`, `order_ref`, `idempotency_key`, `correlation_id`. Response: `reservation_id`, `state`, `reserved_amount`, `expires_at`, `financial_version`. States: `PENDING`, `ACTIVE`, `PARTIALLY_CONSUMED`, `CONSUMED`, `RELEASED`, `EXPIRED`, `REJECTED`.

The same scoped key and payload returns one reservation; a different payload with that key returns `IDEMPOTENCY_CONFLICT`. `release_reservation` is idempotent and cannot release a fully consumed, cross-tenant, or another-account reservation. Application code never updates authoritative availability.
