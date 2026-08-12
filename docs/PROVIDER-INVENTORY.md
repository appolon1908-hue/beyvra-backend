# Provider inventory

Audit date: 2026-08-11. Scope: backend, environment templates, Compose/deploy, workflows, monitoring, docs, and historical adapters. Credential **references** are listed; values were not read or printed. Approval/license means repository evidence, not vendor capability.

| Provider | Category | REST | WebSocket | Webhook | Paper | Live execution | Asset classes | Current adapter | Credential ref | Flag | Approval | License | Current usage |
|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|---|
| CoinGecko | MARKET_DATA, REFERENCE_DATA | yes | vendor capability | vendor capability | no | no | crypto | `wsnotifications` | `COINGECKO_API_KEY[_FILE]` | none | NOT VERIFIED | NOT VERIFIED | legacy REST; disabled as authority |
| Massive / Polygon | MARKET_DATA, REFERENCE_DATA | yes | vendor capability | no | no | no | equity, options, forex, crypto, indices, futures | `portfolio` grouped snapshots | `POLYGON_API_KEY[_FILE]` | none | NOT VERIFIED | NOT VERIFIED | legacy provider-specific endpoints; not authoritative |
| NewsData.io | NEWS | yes | no adapter | no adapter | no | no | news | `news_app` | `NEWS_DATA_API_KEY[_FILE]` | governance row | NOT VERIFIED | NOT VERIFIED | fail-closed without approval |
| Alpaca market data | MARKET_DATA, REFERENCE_DATA | yes | vendor capability | no | no | separate capability | equity, options, crypto | `api_trade` | `API_KEY_ALPACA`, `API_SECRET_ALPACA` | none | NOT VERIFIED | NOT VERIFIED | legacy scripts; not authoritative |
| Alpaca paper | PAPER_TRADING, EXECUTION | yes | yes | no | yes | separate capability | equity, options, crypto | legacy `api_trade` order code | same refs | no enforced `ALPACA_MODE=PAPER` | NOT AUTHORIZED | NOT VERIFIED | must remain disabled |
| Binance public market | MARKET_DATA | yes | yes | no | no | separate code exists elsewhere | crypto | `trade.market_data`, `ws.gateway`, `portfolio` | governance credential file for REST test | governance row | NOT VERIFIED | NOT VERIFIED | fixture-tested, outbound blocked by default |
| Twelve Data | MARKET_DATA | yes | configured URL | no | no | no | equity, forex, crypto | `trade.market_data` | governed mounted file; legacy env also exists | governance row | NOT VERIFIED | NOT VERIFIED | fixture-tested, outbound blocked by default |
| CoinCap | MARKET_DATA | stub | no adapter | no | no | no | crypto | broken legacy factory stub | none | none | NOT VERIFIED | NOT VERIFIED | unused |
| Fixer | REFERENCE_DATA | yes | no | no | no | no | forex | wallet utility | `FIXER_API_KEY` | none | NOT VERIFIED | NOT VERIFIED | legacy utility, outside authority |

`PROVIDER_ACTIVATION_AUTHORIZED=NO`. Credential presence is never approval. Historical credential exposure is documented in `SECURITY_REVIEW.md`; rotation remains external owner action.

