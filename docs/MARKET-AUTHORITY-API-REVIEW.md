# Market Authority API Review

## Canonical endpoints

- `GET /api/v1/market/instruments`
- `GET /api/v1/market/instruments/{instrument_uuid}`
- `GET /api/v1/market/calendar?calendar=XNYS&from=YYYY-MM-DD&to=YYYY-MM-DD`
- `GET /api/v1/market/corporate-actions?instrument_id={instrument_uuid}`
- `GET /api/v1/market/status?instrument_id={instrument_uuid}`
- `GET /api/v1/internal/reference-data/reconciliation` (staff-only)

All endpoints require authentication. Reference data is global and contains no tenant/customer fields. Client-supplied tenant headers cannot select or reveal tenant data. Invalid IDs return the standard DRF not-found contract; provider credentials and topology are never returned.

Provider symbol mappings are excluded from public instrument responses. Staff operators may inspect them through `GET /api/v1/internal/reference-data/provider-mappings/{instrument_uuid}`; customers and support-only users receive `403`.

## Existing API compatibility

Existing snapshot, candle, quote, trade, status, trading-rule, and market-capability routes remain available. Their symbol resolver now prefers the reference authority and uses an effective current provider mapping. The static registry is a documented temporary fallback for unseeded stacked environments.

## Websocket contract

Existing `/ws/v2/` market channels remain transport contracts. New clients should use canonical instrument identity. Provider symbols must be resolved before event publication and must not appear as identity in business events. A later compatibility migration can translate old symbol-based channel names after all clients support UUID channels.

## Adapter review

- CoinGecko: map CoinGecko coin ID/symbol under provider `coingecko`.
- Massive/Polygon: map ticker per product/venue under provider `massive` or the approved canonical provider ID.
- NewsData: map provider market/coin filters under product `NEWS`; articles store canonical instrument refs.
- Future brokers: separate market-data mappings from execution mappings by `product`; live execution remains disabled.
