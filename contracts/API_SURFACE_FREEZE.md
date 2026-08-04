# API surface freeze — Codestra Demo v1

Generated from the Django URL resolver on 2026-08-04.

## Counts

- 200 registered API route patterns (including DRF format variants).
- 197 logical URL templates after format-variant normalization.
- 17 core Demo/tenant/integration/webhook URLs in the product inventory.
- 8 logical webhook-capable URLs, including the legacy Stripe receiver.
- 3 supported legacy WebSocket routes: `/ws/trades/`, `/ws/users/`, and
  `/ws/market-data/`.

The authoritative route inventory is `API_WEBHOOK_INVENTORY.md`; the versioned
OpenAPI document is `contracts/openapi/codestra-demo-v1.yaml`.

## Client drift found during freeze

The current frontend still references contracts not present in the backend
route tree: `platform/config`, `v1/market/snapshot`, `v1/market/candles`,
`v1/economic-calendar`, `v1/realtime/health`, and `ws/v1/*` realtime channels.
These must be implemented behind a versioned service or removed; they must not
silently fall back to mock data.

The frontend also contains direct `fetch()` call sites and legacy payment,
deposit and withdrawal hooks. Those routes remain compatibility-only and must
stay inaccessible from the Demo UI.

## Freeze rules

1. New client calls must use the generated/typed client and a documented
   operation ID.
2. Existing endpoints require contract tests before behavior changes.
3. Any retirement requires a deprecation marker, a migration window and a
   negative test proving the Demo UI cannot call it.
4. No real-money or external order-routing endpoint may be added under the Demo
   product mode.
