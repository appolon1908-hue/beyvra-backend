# Beyvra system architecture review — 2026-08-11

## Decision

The launch architecture is coherent for a paper-trading, fail-closed deployment when the API certification branch is layered on the compliance authority branch. The Django application owns customer-facing authentication, tenant authorization, compliance policy, demo trading, projections, and the canonical `/api/v1/` and `/ws/v2/` contracts. Financial Service remains the sole authority for real wallets, reservations, settlements, deposits, withdrawals, transfers, and provider operations. The browser does not call Financial Service or financial providers directly.

Real value remains unavailable. Real wallet reads, deposits, withdrawals, transfers, trading, external execution, and real money are disabled. Polygon OMS is disabled and halted. No production or provider mutation was performed during this review.

## Contract review

- Backend OpenAPI exposes 325 paths in the reviewed schema.
- The frontend contract scanner now discovers shared-client calls and endpoint constants, not only direct URL interpolation.
- 90 frontend API paths map to the backend schema; unmapped callers are zero.
- Generated frontend paths were aligned with canonical auth, account, market, notification, and integration routes. Compatibility routes remain only where the canonical API does not yet expose equivalent behavior.
- Public financial endpoints remain explicit fail-closed contracts and return `FEATURE_DISABLED` before financial network activity.

## Realtime review

The browser connects to Centrifugo through `/ws/v2/connection/websocket`. Private channels are derived from the authenticated JWT identity for client selection and independently authorized by the backend subscription proxy. The proxy accepts the Beyvra header and retains the legacy Codestra header during migration.

Server-side account ownership checks now cover all account-scoped channels, including `wallet.balance.<account_id>` and portfolio channels. User-scoped notification and compliance channels require exact user identity. Market channels remain public. The event envelope contract requires `event_id`, `event_type`, `schema_version`, `server_timestamp`, and payload; sequence-aware consumers recover gaps through a REST snapshot.

## Financial boundary

Financial Service tests certify that money mutations and real financial reads fail closed. Its Polygon OMS adapter provides guarded, idempotent custodial contracts, unknown-outcome handling, signed webhook verification, and provider-neutral mappings without exposing private keys. Provider balances are reconciliation evidence, not ledger authority.

The application must continue to use only the Financial Service API contract. Direct application SQL against Financial PostgreSQL and direct frontend/provider calls are prohibited.

## Verification evidence

- Backend focused API/compliance/realtime/financial boundary suite: 121 passed on PostgreSQL 16.
- Financial Service contract and OMS suite: 38 passed.
- Frontend unit suite: 86 passed.
- Frontend realtime suite: 4 passed.
- Frontend lint, typecheck, safe-error checks, brand checks, localization checks, API contract validation, and production build: passed.
- Django system check and migration drift check: passed; no model changes were introduced by this review.

## Remaining operational gates

- Public staging E2E, authenticated WebSocket soak/restart/gap recovery, and 500+ connection testing require an approved staging window and synthetic identities.
- The current host has stale orphan containers for retired simulated execution/outbox commands. They are not in the current Compose service graph and should be removed in a controlled staging maintenance window after confirming no retained diagnostic value.
- The frontend bundle reports large-chunk warnings. This is a performance optimization item, not a correctness or financial-safety failure.
- The API certification branch depends on the compliance authority branch and must preserve that review/merge order.

## Certification conclusion

The system makes architectural sense for the present paper-trading scope. API ownership, tenant checks, compliance gating, realtime authorization, and Financial Service authority align. Production readiness is still conditional on the staging-only gates above and independent approvals; this review does not authorize real money or provider activation.
