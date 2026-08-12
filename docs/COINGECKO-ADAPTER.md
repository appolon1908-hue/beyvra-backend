# CoinGecko adapter certification

Official contract checked 2026-08-11. Demo REST root is `https://api.coingecko.com/api/v3/` with `x-cg-demo-api-key`; Pro uses `https://pro-api.coingecko.com/api/v3/` with `x-cg-pro-api-key`. Keys are server-side headers only.

The governed adapter allowlists those hosts and supports coin reference data, market summaries, metadata, and historical charts. It explicitly does not claim bid/ask, genuine depth, execution, accounts, custody, or 5-second bars. Historical granularity and WebSocket access are entitlement-dependent; WebSocket is not enabled.

Credential, license, security, compliance, staging, and production approval are not evidenced, so no live certification call was made and CoinGecko remains disabled.

