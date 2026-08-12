# Instrument and Reference-Data Authority

## Decision

`reference_data.Instrument.instrument_id` is Beyvra's canonical identity. A ticker, venue symbol, ISIN, CUSIP, FIGI, provider symbol, websocket channel, or news keyword is an attribute or mapping and is never identity authority.

The authority is owned by the Beyvra application backend. Financial Service is unchanged and remains the sole financial authority. This layer cannot place orders, execute trades, mutate real balances, or activate providers.

## Boundary

```text
Instrument Master ─┬─ Corporate Actions
                   ├─ Trading Calendars
                   ├─ Provider Symbol Mappings
                   ├─ Market-Data Lineage
                   └─ Market Status Authority
                              │
                              ▼
                    Beyvra Application Backend
                    ├─ /api/v1/market/*
                    ├─ /ws/v2/*
                    ├─ CoinGecko adapter
                    ├─ Massive/Polygon adapter
                    ├─ future broker-data adapters
                    └─ NewsData mapping
```

Provider adapters resolve `(provider_id, product, provider_symbol, effective_at)` to exactly one internal UUID. Mapping intervals may not overlap. Symbol changes create a new effective-dated instrument version and mapping interval; they do not rewrite historical records.

## Core invariants

- One immutable UUID identifies an instrument for its lifetime.
- A current provider symbol resolves to at most one instrument per provider and product.
- Exactly one current `InstrumentVersion` exists for an active instrument.
- Tick and lot sizes are positive decimals.
- Calendar sessions have valid increasing UTC instants or are explicitly closed.
- Corporate-action corrections supersede earlier actions; they do not overwrite them.
- Market-data corrections supersede earlier observations and preserve both payload hashes.
- Every observation records provider, provider event identity, provider symbol, mapping version, observation time, receipt time, and safe payload hash.
- Market status comes from explicit status records, never inferred from a last price.
- Reference audit, market observations, and corporate actions are append-only on PostgreSQL.

## Compatibility retirement

The pre-existing hard-coded market registry remains a temporary fallback so stacked API consumers are not broken before reference data is seeded. Database-backed instruments take precedence. Remove the fallback only after all supported instruments and provider mappings are loaded and API consumers use canonical UUIDs.

## Safety state

`REAL_TRADING_ENABLED=false`, `EXTERNAL_EXECUTION_ENABLED=false`, and `REAL_MONEY_ENABLED=false`. Reference ingestion is read/normalize/store only and cannot authorize outbound execution.
