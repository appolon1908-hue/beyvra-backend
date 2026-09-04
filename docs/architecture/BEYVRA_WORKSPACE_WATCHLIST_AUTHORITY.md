# Beyvra workspace and watchlist authority

This package recovers the useful workspace scope from superseded drafts #55 and #56 as a narrow current-main candidate.

## Authority

`apps.workspace` owns tenant/user presentation state only:

- named watchlists;
- one default watchlist per tenant/user;
- ordered references to canonical instruments;
- mutation versions, idempotency results, and application audit evidence.

It does **not** own instrument identity, market prices, entitlements, orders, positions, balances, risk, execution, settlement, or money movement. Instrument identity remains `reference_data.Instrument`.

## Mutation contract

Every mutation requires:

- `Idempotency-Key`;
- `X-Request-ID`;
- an optional `X-Correlation-ID`;
- the current integer `version` in the JSON body for update, delete, and item mutations.

Exact replays return the original durable result. Reusing a key for different semantics returns `IDEMPOTENCY_CONFLICT`. The tenant-membership row and target watchlist are locked before mutation, so concurrent commands cannot both consume one version.

## Endpoints

```text
GET,POST  /api/v1/watchlists
GET,PATCH,DELETE /api/v1/watchlists/{watchlist_id}
GET,POST /api/v1/watchlists/{watchlist_id}/items
DELETE /api/v1/watchlists/{watchlist_id}/items/{instrument_id}
```

Adding by symbol is allowed only when exactly one active canonical instrument matches. Ambiguous symbols fail closed. Removal by canonical UUID remains possible after an instrument becomes inactive.

## Safety

This package adds no provider call, trading command, wallet/ledger mutation, email delivery, or production activation. It remains application presentation state backed by PostgreSQL.
