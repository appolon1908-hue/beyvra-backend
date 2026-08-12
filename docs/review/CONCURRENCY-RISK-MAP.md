# Concurrency risk map

| Mutation | Current protection | Risk | Status |
|---|---|---|---|
| Demo order create | request idempotency records and database constraints in canonical trading app | competing legacy order paths remain | CONFLICT |
| Cancel/replace versus fill | execution state machine exists only on unmerged stack | no integrated proof | MISSING IN CHECKOUT |
| Demo deposit/withdraw | `atomic` plus wallet `select_for_update` | legacy provider path mutates outside the same transaction | CONFLICT |
| Demo wallet transfer | no atomic transaction, locks, or positive-amount validation | balance creation and lost updates | P1 OPEN |
| Stripe completion | transaction and wallet rows locked; pending status is dedup gate | failed-event path is not locked; legacy shadow balance authority | CONFLICT |
| Application outbox | mutation and outbox model exist | checked-in JetStream topology does not accept `application.*` | P1 OPEN |
| Financial provider operation | Financial Service transaction, uniqueness, RLS and stored procedures | exception-string classification is brittle | REVIEW |
| Financial webhook | Financial Service stored procedure performs dedup/order/transition/outbox | PostgreSQL integration tests required for certification | TEST REQUIRED |

No real-money mutation was exercised during this audit.
